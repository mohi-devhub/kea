"""REST/WS envelope models. CONTRACTS.md sections 3-4."""

from typing import Any, Literal

from pydantic import BaseModel

from app.models.engine import Health
from app.models.topology import Kind, Layout, Tier


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class ServiceNode(BaseModel):
    name: str
    kind: Kind
    tier: Tier
    layout: Layout
    customer_facing: bool
    health: Health = "healthy"


class TopologyEdge(BaseModel):
    source: str
    target: str
    blocking: bool


class TopologyResponse(BaseModel):
    services: list[ServiceNode]
    edges: list[TopologyEdge]


class ScenarioInfo(BaseModel):
    """Never includes ground truth."""

    id: str
    title: str
    description: str
    priority: Literal["P0", "P1"]
    fix_flow_available: bool


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    kafka: bool
    neo4j: bool


class SimulateRequest(BaseModel):
    seed: int
    speed: float | None = None
    skip_warmup: bool = False


class RunRef(BaseModel):
    run_id: str


WsType = Literal[
    "snapshot",
    "run.started",
    "run.stopped",
    "sim.clock",
    "metrics.batch",
    "log.batch",
    "deployment.observed",
    "anomaly.opened",
    "anomaly.resolved",
    "service.health",
    "incident.opened",
    "incident.updated",
    "incident.resolved",
    "prediction.made",
    "prediction.verified",
    "agent.step",
    "agent.done",
    "fix.state",
]


class WsEnvelope(BaseModel):
    type: WsType
    run_id: str | None = None
    seq: int
    sim_ts: int
    payload: Any
