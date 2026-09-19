"""Event schema (Redpanda kea.events.raw, POST /events). CONTRACTS.md section 1."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.models.topology import Metric


class MetricPayload(BaseModel):
    metric: Metric
    value: float


class DeploymentPayload(BaseModel):
    deployment_id: str
    version: str
    commit_ref: str
    summary: str
    author: str


class RollbackPayload(BaseModel):
    deployment_id: str
    restored_version: str


class LogPayload(BaseModel):
    level: Literal["INFO", "WARN", "ERROR"]
    message: str
    fields: dict[str, str | int | float | bool] = {}


class _EventBase(BaseModel):
    schema_version: Literal[1] = 1
    event_id: str  # f"{run_id}:{seq:06d}", used for dedup
    run_id: str
    seq: int
    ts: int  # epoch ms, simulated time, non-decreasing per run
    service: str


class MetricEvent(_EventBase):
    kind: Literal["metric"]
    payload: MetricPayload


class DeploymentEvent(_EventBase):
    kind: Literal["deployment"]
    payload: DeploymentPayload


class RollbackEvent(_EventBase):
    kind: Literal["rollback"]
    payload: RollbackPayload


class LogEvent(_EventBase):
    kind: Literal["log"]
    payload: LogPayload


Event = Annotated[
    MetricEvent | DeploymentEvent | RollbackEvent | LogEvent, Field(discriminator="kind")
]


def make_event_id(run_id: str, seq: int) -> str:
    return f"{run_id}:{seq:06d}"
