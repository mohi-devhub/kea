"""Static topology (scenarios/topology.yaml). CONTRACTS.md section 5."""

from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["service", "database", "cache"]
Tier = Literal["customer_facing", "edge", "internal", "data"]
Metric = Literal[
    "latency_p95_ms",
    "error_rate",
    "request_rate",
    "active_connections",
    "memory_used_pct",
    "cpu_pct",
    "network_delay_ms",
    "packet_loss_pct",
]


class Layout(BaseModel):
    x: float
    y: float


class ServiceDef(BaseModel):
    kind: Kind
    tier: Tier
    layout: Layout


class Edge(BaseModel):
    from_: str = Field(alias="from")
    to: str
    blocking: bool


class Topology(BaseModel):
    services: dict[str, ServiceDef]
    edges: list[Edge]
    metrics: dict[str, dict[Metric, tuple[float, float]]]
    sample_interval_s: int

    @property
    def customer_facing(self) -> set[str]:
        return {n for n, s in self.services.items() if s.tier == "customer_facing"}
