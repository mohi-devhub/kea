"""Public fix-proposal contract (docs/FIX_FLOW_SPEC.md section 4)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FixState = Literal[
    "queued", "generating", "proposed", "approved", "rejected", "failed", "superseded"
]
FixMode = Literal["LIVE", "REPLAYED", "TEMPLATE"]


class _Contract(BaseModel):
    """Fields with defaults are always serialized, so the schema (and the TS types) say required."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class FileChange(_Contract):
    path: str
    additions: int
    deletions: int


class FixExplanation(_Contract):
    summary: str
    why_it_fixes: str
    evidence_ids: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class TestRun(_Contract):
    passed: bool
    summary: str
    output_tail: str = ""


class Verification(_Contract):
    command: str
    before: TestRun | None = None
    after: TestRun | None = None
    tests_modified: bool = False
    modified_tests: list[str] = Field(default_factory=list)


class FixTraceEntry(_Contract):
    step: int
    tool: str
    args_summary: str = ""
    result_summary: str = ""
    duration_ms: int = 0


class ApprovalRecord(_Contract):
    approver: str
    approved_at: str  # wall-clock ISO time; fine here, the fix flow is outside the pure engine
    diff_hash: str


class ApplyStatus(_Contract):
    """Whether approval can change a real repository. Always disabled in the propose-only build."""

    enabled: bool = False
    reason: str = (
        "Not enabled in this build: approval is recorded against the diff hash, "
        "but no branch, commit or PR is created."
    )


class FixProposal(_Contract):
    proposal_id: str
    incident_id: str
    run_id: str
    candidate_id: str
    deployment_id: str
    commit_ref: str
    state: FixState
    backend: str
    mode: FixMode | None = None
    provider: str | None = None
    model: str | None = None
    base_commit: str | None = None
    diff: str = ""
    diff_hash: str | None = None
    files_changed: list[FileChange] = Field(default_factory=list)
    explanation: FixExplanation | None = None
    verification: Verification
    agent_trace: list[FixTraceEntry] = Field(default_factory=list)
    approval: ApprovalRecord | None = None
    apply: ApplyStatus = Field(default_factory=ApplyStatus)
    error: str | None = None
    approvable: bool = False
    approve_blocked_reason: str | None = None


class FixCreated(_Contract):
    proposal_id: str
    incident_id: str
    state: FixState


class ApproveRequest(BaseModel):
    diff_hash: str
    approver: str = "local-user"


class RejectRequest(BaseModel):
    reason: str | None = None
