"""Scale sweep: the same kind of database fault in larger synthetic topologies."""

from typing import Any

from app.eval.runner import EvalRunner
from app.models.topology import Edge, Layout, ServiceDef, Topology
from app.simulator.models import (
    DeploymentSpec,
    EffectSpec,
    ExpectedRejection,
    GroundTruth,
    Recover,
    Remediation,
    RootCause,
    Scenario,
)

SWEEP = (1, 5, 13, 29)  # width of the mid layers; total services = 5 + 2 * width


def build_scaled(width: int) -> tuple[Topology, Scenario]:
    """web -> gateway -> A_i -> B_i -> (postgres | redis), plus a non-blocking decoy service.

    Even B_i depend on postgres (the fault), odd B_i on redis (healthy), so only part of the graph
    cascades and the rest is realistic noise the reader must exclude.
    """
    a = [f"svc-a{i:02d}" for i in range(width)]
    b = [f"svc-b{i:02d}" for i in range(width)]
    services = {
        "web-frontend": ServiceDef(kind="service", tier="customer_facing", layout=Layout(x=0, y=0)),
        "api-gateway": ServiceDef(kind="service", tier="edge", layout=Layout(x=1, y=0)),
        "audit-log": ServiceDef(kind="service", tier="internal", layout=Layout(x=2, y=0)),
        "postgres": ServiceDef(kind="database", tier="data", layout=Layout(x=4, y=0)),
        "redis": ServiceDef(kind="cache", tier="data", layout=Layout(x=4, y=1)),
    }
    edges = [Edge(**{"from": "web-frontend", "to": "api-gateway", "blocking": True})]
    for i in range(width):
        services[a[i]] = ServiceDef(kind="service", tier="customer_facing", layout=Layout(x=2, y=i))
        services[b[i]] = ServiceDef(kind="service", tier="internal", layout=Layout(x=3, y=i))
        data = "postgres" if i % 2 == 0 else "redis"
        for src, dst in (("api-gateway", a[i]), (a[i], b[i]), (b[i], data)):
            edges.append(Edge(**{"from": src, "to": dst, "blocking": True}))
    edges.append(Edge(**{"from": a[0], "to": "audit-log", "blocking": False}))
    web = {
        "latency_p95_ms": (320, 0.05),
        "error_rate": (0.002, 0.0008),
        "request_rate": (120, 0.05),
    }
    mid = {"latency_p95_ms": (150, 0.05), "error_rate": (0.002, 0.0008), "request_rate": (40, 0.05)}
    metrics: dict[str, Any] = {name: mid for name in services}
    metrics["web-frontend"] = metrics["api-gateway"] = web
    metrics["postgres"] = {"latency_p95_ms": (6, 0.05), "active_connections": (40, 0.05)}
    metrics["redis"] = {"latency_p95_ms": (1.2, 0.05), "memory_used_pct": (55, 0.02)}
    topology = Topology(services=services, edges=edges, metrics=metrics, sample_interval_s=5)

    hit = [i for i in range(width) if i % 2 == 0]
    effects = [
        EffectSpec(
            service="postgres", metric="latency_p95_ms", start_s=0, ramp_s=15, target_multiplier=15
        ),
        EffectSpec(
            service="postgres",
            metric="active_connections",
            start_s=45,
            ramp_s=15,
            target_multiplier=3,
        ),
    ]
    effects += [
        EffectSpec(
            service=b[i], metric="latency_p95_ms", start_s=34, ramp_s=15, target_multiplier=15
        )
        for i in hit
    ]
    effects += [
        EffectSpec(service=a[i], metric="error_rate", start_s=70, ramp_s=15, target_value=0.2)
        for i in hit
    ]
    effects += [
        EffectSpec(
            service="api-gateway", metric="error_rate", start_s=115, ramp_s=15, target_value=0.09
        ),
        EffectSpec(
            service="web-frontend", metric="error_rate", start_s=135, ramp_s=15, target_value=0.06
        ),
    ]
    scenario = Scenario(
        id=f"scale_{len(services)}",
        title=f"Database fault, {len(services)} services",
        description="Database fault with a decoy deployment on an unrelated async service.",
        priority="P1",
        warmup_s=270,
        duration_s=180,
        deployments=[
            DeploymentSpec(
                offset_s=-90,
                service="audit-log",
                deployment_id="dep-900",
                version="1.0.1",
                commit_ref="deploy-900",
                summary="Rotate log format",
            ),
        ],
        effects=effects,
        ground_truth=GroundTruth(
            expect_incident=True,
            root_cause=RootCause(kind="service_fault", service="postgres"),
            must_not_implicate=["audit-log"],
            must_reject=[
                ExpectedRejection(
                    candidate_id="deployment:dep-900",
                    reason_code="NO_ANOMALY_ON_SERVICE_OR_REACHABLE",
                )
            ],
            ordering_constraints=[],
        ),
        recover=Recover(
            remediation=Remediation(service="postgres", message="Storage failover completed")
        ),
    )
    return topology, scenario


async def run_sweep(
    runner: EvalRunner, seeds: list[int], approaches: list[str], **providers: Any
) -> dict[str, Any]:
    points: list[dict[str, Any]] = []
    for width in SWEEP:
        topology, scenario = build_scaled(width)
        runner.topology = topology
        report, _ = await runner.run(
            scenarios=[scenario], seeds=seeds, approaches=approaches, **providers
        )
        for row in report["results"]:
            cost = report["cost"].get(row["approach"], {})
            n = row["n"]
            points.append(
                {
                    "services": len(topology.services),
                    "approach": row["approach"],
                    "n": n,
                    "top1_correct": row["top1_correct"]["k"] / n if n else 0.0,
                    "median_tokens": cost.get("median_tokens"),
                    "median_latency_ms": cost.get("median_latency_ms"),
                }
            )
    return {
        "seeds": seeds,
        "points": points,
        "notes": [
            "Same fault shape at every size: a database fault, half the graph cascading, "
            "and a decoy deployment on an async service. Tuning seeds; not the final run.",
        ],
    }
