"""Public investigation result and trace models (AGENT_SPEC.md)."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.engine import BlastRadius, Evidence, RejectedCandidate, WhatChanged


class _Contract(BaseModel):
    """Fields with defaults are always serialized, so the schema (and the TS types) say required."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class NarrativeStep(_Contract):
    text: str
    evidence_ids: list[str] = Field(default_factory=list)


class TraceEntry(_Contract):
    step: int
    kind: Literal["model", "tool", "template", "repair", "error"]
    name: str
    args_summary: str = ""
    result_summary: str = ""
    duration_ms: int = 0


class InvestigationUsage(_Contract):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class InvestigationResult(_Contract):
    investigation_id: str
    incident_id: str
    mode: Literal["LIVE", "REPLAYED", "TEMPLATE"]
    provider: str
    model: str
    summary: str
    root_cause_candidate_id: str | None
    narrative_steps: list[NarrativeStep]
    evidence: list[Evidence]
    blast_radius: BlastRadius
    what_changed: WhatChanged
    rejected_candidates: list[RejectedCandidate]
    caveats: list[str] = Field(default_factory=list)
    disagreement: dict[str, Any] | None = None
    trace: list[TraceEntry] = Field(default_factory=list)
    usage: InvestigationUsage = Field(default_factory=InvestigationUsage)
