"""Fix backends: something that edits files inside a sandbox and reports what it did."""

from dataclasses import dataclass, field
from typing import Protocol

from app.fix.models import FixExplanation, FixMode, FixTraceEntry
from app.fix.sandbox import Sandbox


@dataclass
class FixContext:
    incident_id: str
    candidate_id: str
    deployment_id: str
    commit_ref: str
    incident_summary: str
    evidence: list[dict[str, str]]  # [{evidence_id, statement}]
    failing_output: str


@dataclass
class BackendResult:
    trace: list[FixTraceEntry]
    provider: str
    model: str
    mode: FixMode
    explanation: FixExplanation | None = None
    notes: list[str] = field(default_factory=list)


class FixBackend(Protocol):
    name: str

    async def propose(self, ctx: FixContext, sandbox: Sandbox) -> BackendResult:
        """Edit files inside the sandbox only. Never touch anything outside `sandbox.repo`."""


class BackendUnavailable(RuntimeError):
    pass
