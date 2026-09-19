"""Engine output models. CONTRACTS.md section 2. Score is a heuristic, never a probability."""

from typing import Any, Literal

from pydantic import BaseModel

from app.models.topology import Metric

Health = Literal["healthy", "degraded", "failing"]
Via = Literal["change", "self", "fault", "load"]
ReasonCode = Literal[
    "NO_ANOMALY_ON_SERVICE_OR_REACHABLE",
    "ANOMALY_EXPLAINED_BY_EARLIER_CAUSE",
    "OUTSIDE_LOOKBACK_WINDOW",
    "ANOMALY_PRECEDES_DEPLOYMENT",
]


class Anomaly(BaseModel):
    anomaly_id: str
    run_id: str
    service: str
    metric: Metric
    onset_ts: int
    detected_ts: int
    resolved_ts: int | None = None
    state: Literal["active", "resolved"]
    baseline: float
    peak_value: float
    ratio: float


class Factor(BaseModel):
    value: float
    weight: float
    contribution: float
    explanation: str


class ChainStep(BaseModel):
    step: int
    node_type: Literal["deployment", "anomaly", "service"]
    ref: str
    service: str
    ts: int
    via: Via
    statement: str


class Candidate(BaseModel):
    candidate_id: str
    kind: Literal["deployment", "service_fault"]
    service: str
    deployment_id: str | None = None
    rank: int
    score: float
    factors: dict[str, Factor]
    root_anomaly_ids: list[str]
    covered_anomaly_ids: list[str]
    evidence_ids: list[str]
    chain: list[ChainStep]


class RejectedCandidate(BaseModel):
    candidate_id: str
    service: str
    reason_code: ReasonCode
    statement: str


class Evidence(BaseModel):
    evidence_id: str
    kind: Literal["deployment", "anomaly", "topology", "log"]
    ref: str
    ts: int
    statement: str
    data: dict[str, Any] = {}


class ChangeItem(BaseModel):
    kind: Literal["deployment"]
    deployment_id: str
    service: str
    ts: int
    seconds_before_onset: int
    relevant: bool
    candidate_id: str | None = None
    reason: ReasonCode | None = None


class WhatChanged(BaseModel):
    healthy_until_ts: int
    first_anomaly_ts: int
    changes: list[ChangeItem]
    statement: str


class BlastRadius(BaseModel):
    customer_facing_affected: list[str]
    services: list[str]


class Incident(BaseModel):
    incident_id: str
    run_id: str
    state: Literal["open", "resolved"]
    revision: int  # increments on every change; clients drop stale updates
    opened_ts: int
    first_anomaly_ts: int
    resolved_ts: int | None = None
    anomalies: list[Anomaly]
    service_health: dict[str, Health]
    candidates: list[Candidate]
    rejected_candidates: list[RejectedCandidate]
    ambiguous: bool
    margin: float
    what_changed: WhatChanged
    blast_radius: BlastRadius
    evidence: list[Evidence]


class EngineUpdate(BaseModel):
    run_id: str
    seq: int
    sim_ts: int
    type: Literal[
        "deployment_observed",
        "anomaly_opened",
        "anomaly_resolved",
        "service_health_changed",
        "incident_opened",
        "incident_updated",
        "incident_resolved",
        "pending_watch",
    ]
    payload: dict[str, Any]
