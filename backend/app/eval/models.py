"""Serializable evaluation records."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["deployment", "service_fault"]
    service: str
    deployment_id: str | None = None


class BaselineAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_detected: bool
    ranked_hypotheses: list[Hypothesis] = Field(default_factory=list, max_length=3)
    explanation: str = ""


class Grade(BaseModel):
    top1_correct: bool
    top3_contains: bool
    false_blame: bool
    false_alarm: bool
    decoys_rejected_correctly: bool | None = None
    detection_latency_s: float | None = None
    time_to_correct_s: float | None = None
    grounding_pass: bool | None = None
    ungrounded_claims: int = 0
    evidence_coverage: float | None = None
    decoy_addressed: bool | None = None
    disagreement: bool | None = None
    steps: int | None = None
    mode: str | None = None
    determinism_ok: bool | None = None
    details: dict[str, Any] = Field(default_factory=dict)


RunStatus = Literal["ok", "not_run", "provider_error", "parse_error"]
# not_run and provider_error mean the approach produced no answer at all (infrastructure, not a
# wrong answer), so they are never scored. A parse_error IS scored as incorrect: failing the
# requested output format is the baseline's failure, and it is disclosed.
UNSCORED: frozenset[str] = frozenset({"not_run", "provider_error"})


class RunRecord(BaseModel):
    approach: str
    scenario: str
    seed: int
    run_index: int
    input_sha256: str
    raw_output: str | None = None
    parsed_output: dict[str, Any] | None = None
    grade: Grade
    latency_ms: float | None = None
    usage: dict[str, int | float] = Field(default_factory=dict)
    error: str | None = None
    status: RunStatus = "ok"


class WilsonInterval(BaseModel):
    k: int
    n: int
    ci_low: float
    ci_high: float


class AggregateResult(BaseModel):
    approach: str
    scenario: str
    n: int
    top1_correct: WilsonInterval
    top3_contains: WilsonInterval
    false_blame: WilsonInterval
    false_alarm: WilsonInterval
    unscored: dict[str, int] = Field(default_factory=dict)  # runs excluded from n, by reason
    parse_errors: int = 0  # scored as incorrect, disclosed here
    extra: dict[str, Any] = Field(default_factory=dict)
