"""Fix flow (propose-only): sandbox jail, red-to-green proposal, hash-bound approval, no writes."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from app.config import Settings
from app.engine import InMemoryTopology, run_batch
from app.fix.demo_repo import build_demo_repo
from app.fix.sandbox import Sandbox, SandboxError
from app.fix.service import FixError, FixService
from app.graph.client import load_topology
from app.llm.fake import FakeProvider
from app.llm.models import LLMResponse, Message, ToolCall
from app.simulator.generator import generate
from app.simulator.loader import load_scenarios

BAD = """        conn = pool.acquire()
        if order_id in cache:
            results.append(cache[order_id])
            continue
        results.append(conn.fetch(order_id))
        pool.release(conn)
"""
GOOD = """        if order_id in cache:
            results.append(cache[order_id])
            continue
        with pool.connection() as conn:
            results.append(conn.fetch(order_id))
"""


def _calls(*calls: tuple[str, dict[str, Any]]) -> LLMResponse:
    return LLMResponse(
        message=Message(
            role="assistant",
            tool_calls=[
                ToolCall(id=f"c{i}", name=n, arguments=a) for i, (n, a) in enumerate(calls)
            ],
        ),
        finish_reason="tool_calls",
    )


def _good_fix(evidence_id: str) -> list[LLMResponse]:
    return [
        _calls(
            ("show_commit", {"ref": "deploy-182"}),
            ("read_file", {"path": "src/payments/lookup.py"}),
        ),
        _calls(("apply_edit", {"path": "src/payments/lookup.py", "old": BAD, "new": GOOD})),
        _calls(("run_tests", {})),
        _calls(
            (
                "submit_fix",
                {
                    "summary": "Use one pooled connection per lookup and release it.",
                    "why_it_fixes": "The bad deploy leaked pool connections, per the evidence.",
                    "evidence_ids": [evidence_id],
                    "risks": ["Holds one connection for the whole lookup."],
                },
            )
        ),
    ]


def _repo_state(repo: Path) -> tuple[str, str, str]:
    def git(*a: str) -> str:
        return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True).stdout

    return git("rev-parse", "HEAD"), git("branch", "-a"), git("status", "--porcelain")


@pytest.fixture
def world(tmp_path: Path) -> dict[str, Any]:
    settings = Settings(_env_file=None)
    topology = load_topology(settings.topology_path)
    scenarios = {s.id: s for s in load_scenarios(settings.topology_path.parent, topology)}
    out = {}
    for sid in ("s1_bad_deploy_payment", "s2_postgres_degradation"):
        events = generate(scenarios[sid], topology, 0)
        incident = run_batch(events, InMemoryTopology(topology)).incident
        deployments = [e.model_dump(mode="json") for e in events if e.kind == "deployment"]
        out[sid] = (incident, deployments)
    repo = build_demo_repo(tmp_path / "demo")
    return {"scenarios": out, "repo": repo, "tmp": tmp_path}


def _service(world: dict[str, Any], provider: FakeProvider | None, **kw: Any) -> FixService:
    return FixService(
        demo_repo=world["repo"],
        sandboxes=world["tmp"] / "sandboxes",
        provider=provider,
        backend_pref="llm_tool_loop",
        codex_binary="definitely-not-installed",
        **kw,
    )


def test_demo_repo_is_red_on_the_bad_commit_and_green_after_the_fix(tmp_path: Path) -> None:
    repo = build_demo_repo(tmp_path / "demo")
    sandbox = Sandbox.create(repo, tmp_path / "sb", "FIX-x")
    assert not sandbox.run_tests().passed
    target = sandbox.repo / "src/payments/lookup.py"
    target.write_text(target.read_text().replace(BAD, GOOD))
    assert sandbox.run_tests().passed


def test_sandbox_rejects_traversal_absolute_paths_and_symlink_escapes(tmp_path: Path) -> None:
    repo = build_demo_repo(tmp_path / "demo")
    sandbox = Sandbox.create(repo, tmp_path / "sb", "FIX-x")
    (tmp_path / "secret.txt").write_text("nope")
    (sandbox.repo / "link").symlink_to(tmp_path / "secret.txt")
    for bad in ("../secret.txt", "/etc/passwd", ".git/config", "link", ""):
        with pytest.raises(SandboxError):
            sandbox.resolve(bad)


async def test_proposal_goes_red_to_green_without_touching_the_real_repo(
    world: dict[str, Any],
) -> None:
    incident, deployments = world["scenarios"]["s1_bad_deploy_payment"]
    before = _repo_state(world["repo"])
    svc = _service(world, FakeProvider(_good_fix(incident.evidence[0].evidence_id)))
    created = await svc.start(incident, incident.run_id, deployments)
    await svc.wait(created.proposal_id)
    proposal = svc.get(created.proposal_id)
    assert proposal.state == "proposed", proposal.error
    assert proposal.verification.before and not proposal.verification.before.passed
    assert proposal.verification.after and proposal.verification.after.passed
    assert proposal.approvable and not proposal.verification.tests_modified
    assert proposal.diff_hash and proposal.diff_hash.startswith("sha256:")
    assert [f.path for f in proposal.files_changed] == ["src/payments/lookup.py"]
    assert proposal.explanation and proposal.mode == "LIVE"
    assert _repo_state(world["repo"]) == before  # acceptance 2: real repo byte-identical


async def test_approval_is_bound_to_the_diff_hash_and_applies_nothing(
    world: dict[str, Any],
) -> None:
    incident, deployments = world["scenarios"]["s1_bad_deploy_payment"]
    before = _repo_state(world["repo"])
    svc = _service(world, FakeProvider(_good_fix(incident.evidence[0].evidence_id)))
    created = await svc.start(incident, incident.run_id, deployments)
    await svc.wait(created.proposal_id)
    with pytest.raises(FixError) as wrong:
        await svc.approve(created.proposal_id, "sha256:" + "0" * 64, "tester")
    assert wrong.value.status == 409 and svc.get(created.proposal_id).state == "proposed"
    good_hash = svc.get(created.proposal_id).diff_hash or ""
    approved = await svc.approve(created.proposal_id, good_hash, "tester")
    again = await svc.approve(created.proposal_id, good_hash, "tester")  # idempotent
    assert approved.state == "approved" and again.approval == approved.approval
    assert approved.approval and approved.approval.diff_hash == good_hash
    assert approved.apply.enabled is False  # visibly disabled in this build
    assert _repo_state(world["repo"]) == before  # nothing was applied anywhere
    assert not (world["tmp"] / "sandboxes" / created.proposal_id).exists()


async def test_a_proposal_that_edits_existing_tests_cannot_be_approved(
    world: dict[str, Any],
) -> None:
    incident, deployments = world["scenarios"]["s1_bad_deploy_payment"]
    tamper = [
        _calls(
            (
                "apply_edit",
                {
                    "path": "tests/test_lookup.py",
                    "old": "self.assertEqual(pool.outstanding, 0)",
                    "new": "pass",
                },
            )
        ),
        _calls(("apply_edit", {"path": "src/payments/lookup.py", "old": BAD, "new": GOOD})),
        _calls(("submit_fix", {"summary": "x.", "why_it_fixes": "y."})),
    ]
    svc = _service(world, FakeProvider(tamper))
    created = await svc.start(incident, incident.run_id, deployments)
    await svc.wait(created.proposal_id)
    proposal = svc.get(created.proposal_id)
    # the tool refuses edits outside src/, so the tests stay intact and the fix is still valid
    assert not proposal.verification.tests_modified
    assert proposal.files_changed and all(f.path.startswith("src/") for f in proposal.files_changed)


async def test_red_proposal_is_not_approvable(world: dict[str, Any]) -> None:
    incident, deployments = world["scenarios"]["s1_bad_deploy_payment"]
    lazy = [
        _calls(
            (
                "apply_edit",
                {
                    "path": "src/payments/lookup.py",
                    "old": "results = []",
                    "new": "results = []  # noop",
                },
            )
        ),
        _calls(("submit_fix", {"summary": "x.", "why_it_fixes": "y."})),
    ]
    svc = _service(world, FakeProvider(lazy))
    created = await svc.start(incident, incident.run_id, deployments)
    await svc.wait(created.proposal_id)
    proposal = svc.get(created.proposal_id)
    assert proposal.state == "proposed" and not proposal.approvable
    assert proposal.approve_blocked_reason
    with pytest.raises(FixError):
        await svc.approve(created.proposal_id, proposal.diff_hash or "", "tester")


async def test_non_deployment_root_cause_offers_no_fix(world: dict[str, Any]) -> None:
    incident, deployments = world["scenarios"]["s2_postgres_degradation"]
    svc = _service(world, FakeProvider())
    with pytest.raises(FixError) as err:
        await svc.start(incident, incident.run_id, deployments)
    assert err.value.status == 409 and "not a code change" in err.value.message


async def test_no_backend_fails_with_a_readable_message(world: dict[str, Any]) -> None:
    incident, deployments = world["scenarios"]["s1_bad_deploy_payment"]
    svc = _service(world, None)
    created = await svc.start(incident, incident.run_id, deployments)
    await svc.wait(created.proposal_id)
    proposal = svc.get(created.proposal_id)
    assert proposal.state == "failed" and "No fix backend" in (proposal.error or "")


async def test_regenerate_supersedes_the_previous_proposal(world: dict[str, Any]) -> None:
    incident, deployments = world["scenarios"]["s1_bad_deploy_payment"]
    ev = incident.evidence[0].evidence_id
    svc = _service(world, FakeProvider(_good_fix(ev) + _good_fix(ev)))
    first = await svc.start(incident, incident.run_id, deployments)
    await svc.wait(first.proposal_id)
    second = await svc.regenerate(first.proposal_id, deployments)
    await svc.wait(second.proposal_id)
    assert svc.get(first.proposal_id).state == "superseded"
    assert svc.get(second.proposal_id).state == "proposed"


async def test_record_then_replay_serves_the_diff_and_still_runs_tests(
    world: dict[str, Any],
) -> None:
    incident, deployments = world["scenarios"]["s1_bad_deploy_payment"]
    cache = world["tmp"] / "cache"
    ev = incident.evidence[0].evidence_id
    live = _service(world, FakeProvider(_good_fix(ev)), cache_mode="record", cache_dir=cache)
    first = await live.start(incident, incident.run_id, deployments)
    await live.wait(first.proposal_id)
    replay = _service(world, FakeProvider(), cache_mode="replay", cache_dir=cache)
    second = await replay.start(incident, incident.run_id, deployments)
    await replay.wait(second.proposal_id)
    proposal = replay.get(second.proposal_id)
    assert proposal.mode == "REPLAYED" and proposal.state == "proposed"
    assert proposal.verification.after and proposal.verification.after.passed
    assert proposal.diff_hash == live.get(first.proposal_id).diff_hash


def test_only_apply_module_is_reserved_for_repo_writes() -> None:
    """No module besides apply.py may run a git command that mutates a repository."""
    root = Path(__file__).resolve().parents[1] / "app" / "fix"
    writes = ('"commit"', '"checkout"', '"push"', '"merge"', '"branch",')
    for path in root.rglob("*.py"):
        if path.name in {"apply.py", "demo_repo.py"}:
            continue
        text = path.read_text()
        assert not any(w in text for w in writes), f"{path.name} runs a git write"
    assert "apply_approved(" not in (root / "service.py").read_text().replace("import", "")


def test_secrets_never_reach_the_sandbox_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.fix.sandbox import _clean_env

    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    env = _clean_env(tmp_path)
    assert "GITHUB_TOKEN" not in env and "OPENAI_API_KEY" not in env
    assert "ghp_secret" not in json.dumps(env) and "sk-secret" not in json.dumps(env)


class _TamperingBackend:
    """Stands in for an agent that weakens a test instead of fixing the bug."""

    name = "tamper"

    async def propose(self, ctx: Any, sandbox: Sandbox) -> Any:
        from app.fix.backends import BackendResult

        test = sandbox.repo / "tests/test_lookup.py"
        test.write_text(test.read_text().replace("self.assertEqual(pool.outstanding, 0)", "pass"))
        return BackendResult(trace=[], provider="fake", model="fake", mode="LIVE")


async def test_weakening_an_existing_test_makes_the_proposal_unapprovable(
    world: dict[str, Any],
) -> None:
    incident, deployments = world["scenarios"]["s1_bad_deploy_payment"]
    svc = _service(world, None)
    svc._select_backend = lambda: _TamperingBackend()  # type: ignore[method-assign]
    created = await svc.start(incident, incident.run_id, deployments)
    await svc.wait(created.proposal_id)
    proposal = svc.get(created.proposal_id)
    assert proposal.verification.after and proposal.verification.after.passed  # green, but forged
    assert proposal.verification.tests_modified and not proposal.approvable
    with pytest.raises(FixError) as err:
        await svc.approve(created.proposal_id, proposal.diff_hash or "", "tester")
    assert err.value.status == 409 and "existing tests" in err.value.message
