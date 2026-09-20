"""Fix-proposal lifecycle: generate in a sandbox, verify, explain, approve by hash (F1).

State machine (docs/FIX_FLOW_SPEC.md section 5), enforced in one place:
    queued -> generating -> proposed --approve--> approved
                  |             |--reject--> rejected
                  v             |--regenerate--> superseded
                failed
"""

import asyncio
import hashlib
import json
import subprocess
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.fix.apply import ApprovedToken
from app.fix.backends import BackendResult, BackendUnavailable, FixBackend, FixContext
from app.fix.backends.codex_cli import CodexCliBackend
from app.fix.backends.llm_tool_loop import LLMToolLoopBackend
from app.fix.demo_repo import TEST_COMMAND, build_demo_repo, has_tag
from app.fix.explain import template_explanation, validate_explanation
from app.fix.models import (
    ApprovalRecord,
    FixExplanation,
    FixProposal,
    FixState,
    FixTraceEntry,
    Verification,
)
from app.fix.sandbox import MAX_CHANGED_LINES, Sandbox, changed_lines, diff_hash
from app.llm.base import LLMProvider
from app.models.engine import Incident

PROMPT_VERSION = "fix-v1"
BACKEND_TIMEOUT_S = 180
ACTIVE: set[str] = {"queued", "generating", "proposed"}
TRANSITIONS: dict[str, set[str]] = {
    "queued": {"generating", "failed", "superseded"},
    "generating": {"proposed", "failed", "superseded"},
    "proposed": {"approved", "rejected", "superseded"},
    "approved": set(),
    "rejected": set(),
    "failed": set(),
    "superseded": set(),
}

Broadcast = Callable[[dict[str, Any]], Awaitable[None]]


class FixError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class FixService:
    def __init__(
        self,
        *,
        demo_repo: Path,
        sandboxes: Path,
        provider: LLMProvider | None,
        backend_pref: str = "codex_cli",
        cache_mode: str = "off",
        cache_dir: Path | None = None,
        broadcast: Broadcast | None = None,
        codex_binary: str = "codex",
    ) -> None:
        self.demo_repo = demo_repo
        self.sandboxes = sandboxes
        self.provider = provider
        self.backend_pref = backend_pref
        self.cache_mode = cache_mode
        self.cache_dir = cache_dir
        self.broadcast = broadcast
        self.codex_binary = codex_binary
        self.proposals: dict[str, FixProposal] = {}
        self._sandboxes: dict[str, Sandbox] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._meta: dict[str, tuple[Incident, str]] = {}  # proposal_id -> (incident, run_id)

    # ---------------------------------------------------------------- public API

    def eligibility(self, incident: Incident, deployments: list[dict[str, Any]]) -> tuple[str, str]:
        """(deployment_id, commit_ref) for the top candidate, or raise FixError(409)."""
        top = incident.candidates[0] if incident.candidates else None
        if top is None or top.kind != "deployment" or not top.deployment_id:
            raise FixError(409, "No fix proposal available: the root cause is not a code change.")
        commit_ref = next(
            (
                str(d["payload"]["commit_ref"])
                for d in deployments
                if d.get("payload", {}).get("deployment_id") == top.deployment_id
            ),
            "",
        )
        self.ensure_demo_repo()
        if not commit_ref or not has_tag(self.demo_repo, commit_ref):
            raise FixError(
                409,
                f"No fix proposal available: {commit_ref or 'the commit'} is not in the demo repo.",
            )
        return top.deployment_id, commit_ref

    def ensure_demo_repo(self) -> None:
        if not has_tag(self.demo_repo, "deploy-182"):
            build_demo_repo(self.demo_repo)

    async def start(
        self, incident: Incident, run_id: str, deployments: list[dict[str, Any]]
    ) -> FixProposal:
        deployment_id, commit_ref = await asyncio.to_thread(self.eligibility, incident, deployments)
        for old in list(self.proposals.values()):
            if old.incident_id == incident.incident_id and old.state in ACTIVE:
                await self._transition(
                    old.proposal_id, "superseded", message="superseded by a new proposal"
                )
                self._destroy(old.proposal_id)
        proposal_id = f"FIX-{uuid.uuid4().hex[:8]}"
        proposal = FixProposal(
            proposal_id=proposal_id,
            incident_id=incident.incident_id,
            run_id=run_id,
            candidate_id=incident.candidates[0].candidate_id,
            deployment_id=deployment_id,
            commit_ref=commit_ref,
            state="queued",
            backend=self.backend_pref,
            verification=Verification(command=" ".join(TEST_COMMAND)),
        )
        self.proposals[proposal_id] = proposal
        self._meta[proposal_id] = (incident, run_id)
        self._locks[proposal_id] = asyncio.Lock()
        await self._emit(proposal, "queued")
        self._tasks[proposal_id] = asyncio.create_task(self._generate(proposal_id))
        return proposal

    def get(self, proposal_id: str) -> FixProposal:
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            raise FixError(404, "fix proposal not found")
        return proposal

    async def approve(self, proposal_id: str, presented_hash: str, approver: str) -> FixProposal:
        """Record a human approval bound to the exact diff hash. Nothing is applied (F1)."""
        proposal = self.get(proposal_id)
        async with self._locks[proposal_id]:
            if proposal.state == "approved":  # idempotent: same approval, nothing new happens
                if proposal.approval and proposal.approval.diff_hash == presented_hash:
                    return proposal
                raise FixError(409, "diff hash does not match the approved proposal")
            if proposal.state != "proposed":
                raise FixError(409, f"cannot approve a proposal in state {proposal.state}")
            if not proposal.diff_hash or presented_hash != proposal.diff_hash:
                raise FixError(
                    409, "diff hash mismatch: the proposal changed or was not the one reviewed"
                )
            if not proposal.approvable:
                raise FixError(409, proposal.approve_blocked_reason or "proposal is not approvable")
            _ = ApprovedToken(
                proposal_id, proposal.diff_hash, approver
            )  # minted, deliberately unused
            proposal.approval = ApprovalRecord(
                approver=approver,
                approved_at=datetime.now(UTC).isoformat(timespec="seconds"),
                diff_hash=proposal.diff_hash,
            )
            await self._transition(
                proposal_id, "approved", message="approved; apply is not enabled"
            )
            self._destroy(proposal_id)
            return proposal

    async def reject(self, proposal_id: str, reason: str | None = None) -> FixProposal:
        proposal = self.get(proposal_id)
        async with self._locks[proposal_id]:
            if proposal.state != "proposed":
                raise FixError(409, f"cannot reject a proposal in state {proposal.state}")
            await self._transition(proposal_id, "rejected", message=reason or "rejected")
            self._destroy(proposal_id)
            return proposal

    async def regenerate(self, proposal_id: str, deployments: list[dict[str, Any]]) -> FixProposal:
        self.get(proposal_id)
        incident, run_id = self._meta[proposal_id]
        return await self.start(incident, run_id, deployments)

    def reset(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        for proposal_id in list(self._sandboxes):
            self._destroy(proposal_id)
        self.proposals.clear()
        self._meta.clear()
        self._locks.clear()
        self._tasks.clear()

    async def wait(self, proposal_id: str) -> None:
        task = self._tasks.get(proposal_id)
        if task:
            await task

    # ---------------------------------------------------------------- generation

    def _select_backend(self) -> FixBackend:
        if self.backend_pref == "codex_cli":
            codex = CodexCliBackend(self.codex_binary)
            if codex.available():
                return codex
        if self.provider is not None:
            return LLMToolLoopBackend(self.provider)
        raise BackendUnavailable(
            "No fix backend available: install the Codex CLI or configure an LLM provider."
        )

    async def _generate(self, proposal_id: str) -> None:
        proposal = self.proposals[proposal_id]
        incident, _ = self._meta[proposal_id]
        try:
            await self._transition(proposal_id, "generating")
            sandbox = await asyncio.to_thread(
                Sandbox.create, self.demo_repo, self.sandboxes, proposal_id
            )
            self._sandboxes[proposal_id] = sandbox
            proposal.base_commit = sandbox.base_commit
            before = await asyncio.to_thread(sandbox.run_tests)
            proposal.verification.before = before
            evidence = [
                {"evidence_id": e.evidence_id, "statement": e.statement} for e in incident.evidence
            ]
            ctx = FixContext(
                incident_id=incident.incident_id,
                candidate_id=proposal.candidate_id,
                deployment_id=proposal.deployment_id,
                commit_ref=proposal.commit_ref,
                incident_summary=incident.what_changed.statement,
                evidence=evidence,
                failing_output=before.output_tail,
            )
            backend = self._select_backend()
            proposal.backend = backend.name
            result = await self._run_backend(proposal, backend, ctx, sandbox, evidence)
            await self._finish(proposal, sandbox, result, evidence)
        except (BackendUnavailable, FixError, subprocess.SubprocessError, OSError) as exc:
            await self._fail(proposal_id, str(exc))
        except TimeoutError:
            await self._fail(proposal_id, f"the fix backend timed out after {BACKEND_TIMEOUT_S}s")
        except Exception as exc:  # a proposal failure must never crash the API
            await self._fail(proposal_id, f"{type(exc).__name__}: {str(exc)[:200]}")

    def _cache_key(
        self, proposal: FixProposal, ctx: FixContext, backend: FixBackend
    ) -> Path | None:
        if self.cache_mode not in {"record", "replay"} or self.cache_dir is None:
            return None
        blob = json.dumps(
            [
                ctx.evidence,
                proposal.base_commit,
                backend.name,
                getattr(self.provider, "model", ""),
                PROMPT_VERSION,
            ],
            sort_keys=True,
        )
        return self.cache_dir / f"{hashlib.sha256(blob.encode()).hexdigest()}.json"

    async def _run_backend(
        self,
        proposal: FixProposal,
        backend: FixBackend,
        ctx: FixContext,
        sandbox: Sandbox,
        evidence: list[dict[str, str]],
    ) -> BackendResult:
        cache = self._cache_key(proposal, ctx, backend)
        if cache is not None and self.cache_mode == "replay":
            if not cache.exists():
                raise FixError(500, "replay mode: no recorded fix for this incident")
            saved = json.loads(cache.read_text("utf-8"))
            await asyncio.to_thread(_git_apply, sandbox, saved["diff"])
            return BackendResult(
                trace=[
                    FixTraceEntry(step=1, tool="replay", result_summary="applied recorded diff")
                ],
                provider=saved["provider"],
                model=saved["model"],
                mode="REPLAYED",
                explanation=FixExplanation.model_validate(saved["explanation"])
                if saved.get("explanation")
                else None,
            )
        result = await asyncio.wait_for(backend.propose(ctx, sandbox), timeout=BACKEND_TIMEOUT_S)
        if cache is not None:  # record mode: remember the edit, still verified live on replay
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(
                json.dumps(
                    {
                        "diff": await asyncio.to_thread(sandbox.diff),
                        "provider": result.provider,
                        "model": result.model,
                        "explanation": result.explanation.model_dump()
                        if result.explanation
                        else None,
                    }
                ),
                "utf-8",
            )
        return result

    async def _finish(
        self,
        proposal: FixProposal,
        sandbox: Sandbox,
        result: BackendResult,
        evidence: list[dict[str, str]],
    ) -> None:
        diff = await asyncio.to_thread(sandbox.diff)
        files = await asyncio.to_thread(sandbox.files_changed)
        if not diff.strip():
            raise FixError(500, "the backend made no changes")
        if changed_lines(files) > MAX_CHANGED_LINES:
            raise FixError(500, f"the change is larger than {MAX_CHANGED_LINES} lines")
        bad = await asyncio.to_thread(sandbox.disallowed_edits)
        tests_touched = await asyncio.to_thread(sandbox.modified_tests)
        after = await asyncio.to_thread(sandbox.run_tests)
        explanation = result.explanation
        if explanation is None or validate_explanation(
            explanation, files, {e["evidence_id"] for e in evidence}
        ):
            explanation = template_explanation(files, proposal.candidate_id, evidence)
        proposal.diff = diff
        proposal.diff_hash = diff_hash(diff)
        proposal.files_changed = files
        proposal.explanation = explanation
        proposal.agent_trace = result.trace
        proposal.provider, proposal.model, proposal.mode = (
            result.provider,
            result.model,
            result.mode,
        )
        proposal.verification.after = after
        proposal.verification.tests_modified = bool(tests_touched)
        proposal.verification.modified_tests = tests_touched
        reason = None
        if not after.passed:
            reason = "The tests still fail after the change."
        elif tests_touched:
            reason = "The change modifies existing tests: " + ", ".join(tests_touched)
        elif bad:
            reason = "The change touches files outside src/: " + ", ".join(bad)
        proposal.approvable = reason is None
        proposal.approve_blocked_reason = reason
        await self._transition(proposal.proposal_id, "proposed")

    # ---------------------------------------------------------------- state and cleanup

    async def _transition(
        self, proposal_id: str, new: FixState, message: str | None = None
    ) -> None:
        proposal = self.proposals[proposal_id]
        if new not in TRANSITIONS[proposal.state]:
            raise FixError(409, f"invalid transition {proposal.state} -> {new}")
        proposal.state = new
        await self._emit(proposal, message)

    async def _fail(self, proposal_id: str, message: str) -> None:
        proposal = self.proposals[proposal_id]
        proposal.error = message
        if "failed" in TRANSITIONS[proposal.state]:
            await self._transition(proposal_id, "failed", message)
        self._destroy(proposal_id)

    def _destroy(self, proposal_id: str) -> None:
        sandbox = self._sandboxes.pop(proposal_id, None)
        if sandbox:
            sandbox.destroy()

    async def _emit(self, proposal: FixProposal, message: str | None) -> None:
        if self.broadcast is None:
            return
        await self.broadcast(
            {
                "type": "fix.state",
                "run_id": proposal.run_id,
                "seq": 0,
                "sim_ts": 0,
                "payload": {
                    "proposal_id": proposal.proposal_id,
                    "incident_id": proposal.incident_id,
                    "state": proposal.state,
                    "message": message,
                    "mode": proposal.mode,
                },
            }
        )


def _git_apply(sandbox: Sandbox, diff: str) -> None:
    subprocess.run(
        ["git", "apply", "--whitespace=nowarn", "-"],
        cwd=sandbox.repo, input=diff, text=True, check=True, capture_output=True, timeout=30,
    )  # fmt: skip
