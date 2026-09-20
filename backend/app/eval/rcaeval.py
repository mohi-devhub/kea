"""RCAEval adapter for the frozen RE1/RE2 Online Boutique and RE1 Sock Shop splits.

Mapping frozen BEFORE the first run (no tuning on results):
  latency-90 (s) -> latency_p95_ms (x1000), workload -> request_rate, error -> error_rate,
  mem (bytes) -> memory_used_pct = 100 * mem / (2 * pre-injection median),
  cpu (%) -> cpu_pct, latency-90 - latency-50 (s) -> network_delay_ms (x1000),
  socket count -> packet_loss_pct = max(0, 100 * (socket - pre-injection median) /
  max(pre-injection median, 1)). The socket-derived packet-loss value is explicitly a proxy;
  RCAEval does not publish a packet-loss counter. disk/diskio remains unmapped.
Samples are 1 Hz in the source and subsampled to every 5th second (the engine's cadence).
This exercises the service-fault path only; RCAEval has no deployment events.
"""

import json
import urllib.request
from pathlib import Path
from statistics import median
from typing import Any

from app.eval.runner import EvalRunner
from app.models.events import Event, MetricEvent, MetricPayload
from app.models.topology import Edge, Layout, ServiceDef, Topology
from app.simulator.generator import EPOCH_MS
from app.simulator.models import GroundTruth, RootCause, Scenario

HF = "https://huggingface.co/datasets/phamquiluan/RCAEval/resolve/main"
ROOT_SERVICES = (
    "adservice",
    "cartservice",
    "checkoutservice",
    "currencyservice",
    "productcatalogservice",
)
SOCK_SHOP_ROOT_SERVICES = ("carts", "catalogue", "orders", "payment", "user")
FAULTS = ("cpu", "mem", "disk", "delay", "loss")
RE2_FAULTS = (*FAULTS, "socket")
_CALLS = {
    "frontend": (
        "adservice",
        "cartservice",
        "checkoutservice",
        "currencyservice",
        "productcatalogservice",
        "recommendationservice",
        "shippingservice",
    ),
    "checkoutservice": (
        "cartservice",
        "currencyservice",
        "emailservice",
        "paymentservice",
        "productcatalogservice",
        "shippingservice",
    ),
    "cartservice": ("redis",),
    "recommendationservice": ("productcatalogservice",),
}
_SOCK_SHOP_CALLS = {
    "front-end": ("carts", "catalogue", "orders", "user"),
    "carts": ("carts-db", "catalogue"),
    "catalogue": ("catalogue-db",),
    "orders": ("orders-db", "payment", "shipping", "user", "queue-master"),
    "user": ("user-db", "session-db"),
    "queue-master": ("rabbitmq",),
    "rabbitmq-exporter": ("rabbitmq",),
}
_METRIC = {"latency-90": "latency_p95_ms", "workload": "request_rate", "error": "error_rate"}
RCAEVAL_METRIC_MAPPING = {
    "cpu": "cpu_pct",
    "error": "error_rate",
    "latency-50+latency-90": "network_delay_ms",
    "latency-90": "latency_p95_ms",
    "mem": "memory_used_pct",
    "socket": "packet_loss_pct (proxy)",
    "workload": "request_rate",
}


def online_boutique() -> Topology:
    names = {"frontend", "redis", *(c for callees in _CALLS.values() for c in callees), *_CALLS}
    services = {
        n: ServiceDef(
            kind="cache" if n == "redis" else "service",
            tier="customer_facing" if n == "frontend" else "internal",
            layout=Layout(x=0, y=0),
        )
        for n in sorted(names)
    }
    edges = [Edge(**{"from": a, "to": b, "blocking": True}) for a, bs in _CALLS.items() for b in bs]
    return Topology(
        services=services, edges=edges, metrics={n: {} for n in services}, sample_interval_s=5
    )


def sock_shop() -> Topology:
    names = {
        "front-end",
        "rabbitmq-exporter",
        *(c for callees in _SOCK_SHOP_CALLS.values() for c in callees),
        *_SOCK_SHOP_CALLS,
    }
    services = {
        n: ServiceDef(
            kind=("database" if n.endswith("-db") else "cache" if n == "rabbitmq" else "service"),
            tier=(
                "customer_facing"
                if n == "front-end"
                else "data"
                if n.endswith("-db")
                else "internal"
            ),
            layout=Layout(x=0, y=0),
        )
        for n in sorted(names)
    }
    edges = [
        Edge(**{"from": caller, "to": callee, "blocking": True})
        for caller, callees in _SOCK_SHOP_CALLS.items()
        for callee in callees
    ]
    return Topology(
        services=services, edges=edges, metrics={n: {} for n in services}, sample_interval_s=5
    )


def topology_for_case(case: str) -> Topology:
    if case.startswith(("re1ss_", "re2ss_")):
        return sock_shop()
    return online_boutique()


def case_names(reps: int = 1) -> list[str]:
    return [f"re1ob_{s}_{f}_{r}" for s in ROOT_SERVICES for f in FAULTS for r in range(1, reps + 1)]


def fetch(case: str, cache: Path) -> Path:
    target = cache / case
    target.mkdir(parents=True, exist_ok=True)
    for name in ("metrics.parquet", "inject_time.txt"):
        if not (target / name).exists():
            urllib.request.urlretrieve(f"{HF}/{case}/{name}", target / name)  # noqa: S310
    return target


def load_case(case: str, directory: Path, topology: Topology) -> tuple[list[Event], Scenario]:
    import pyarrow.parquet as pq  # optional dependency group: rcaeval

    table = pq.read_table(directory / "metrics.parquet").to_pydict()
    inject = int((directory / "inject_time.txt").read_text().strip())
    times: list[int] = table["time"]
    start = times[0]
    keep = [i for i, t in enumerate(times) if (t - start) % 5 == 0]
    events: list[Event] = []
    for column, values in table.items():
        service, _, raw = column.partition("_")
        if service not in topology.services:
            continue
        if raw == "mem":
            pre = [v for v, t in zip(values, times, strict=True) if t < inject and v is not None]
            if not pre:
                continue
            baseline = median(pre)
            series = [100 * v / (2 * baseline) if v is not None else None for v in values]
            metric = "memory_used_pct"
        elif raw in _METRIC:
            scale = 1000 if raw == "latency-90" else 1
            series, metric = [v * scale if v is not None else None for v in values], _METRIC[raw]
        else:
            continue
        for i in keep:
            if series[i] is not None:
                events.append(
                    MetricEvent(
                        kind="metric", event_id="", run_id=case, seq=0, service=service,
                        ts=EPOCH_MS + (times[i] - start) * 1000,
                        payload=MetricPayload(metric=metric, value=float(series[i])),  # type: ignore[arg-type]
                    )
                )  # fmt: skip
    events.sort(key=lambda e: (e.ts, e.service, e.payload.metric))  # type: ignore[union-attr]
    events = [
        e.model_copy(update={"seq": n, "event_id": f"{case}:{n:06d}"}) for n, e in enumerate(events)
    ]
    service = case.split("_")[1]
    warmup = inject - start
    scenario = Scenario(
        id=case, title=case, description="RCAEval RE1-OB real fault injection", priority="P1",
        warmup_s=warmup, duration_s=times[-1] - inject, deployments=[], effects=[],
        ground_truth=GroundTruth(
            expect_incident=True, root_cause=RootCause(kind="service_fault", service=service),
            must_not_implicate=[], must_reject=[], ordering_constraints=[],
        ),
    )  # fmt: skip
    return events, scenario


async def run_rcaeval(
    runner: EvalRunner, cache: Path, cases: list[str], approaches: list[str], **providers: Any
) -> dict[str, Any]:
    topology = online_boutique()
    runner.topology = topology
    loaded = {c: load_case(c, fetch(c, cache), topology) for c in cases}
    report, _ = await runner.run(
        scenarios=[s for _, s in loaded.values()], seeds=[0], approaches=approaches,
        events_for=lambda scenario, _seed: loaded[scenario.id][0], **providers,
    )  # fmt: skip
    by_fault: dict[str, dict[str, list[bool]]] = {}
    for row in report["results"]:
        fault = row["scenario"].split("_")[2]
        bucket = by_fault.setdefault(row["approach"], {}).setdefault(fault, [])
        bucket += [True] * row["top1_correct"]["k"] + [False] * (
            row["n"] - row["top1_correct"]["k"]
        )
    return {
        "cases": len(cases),
        "results": report["results"],
        "cost": report["cost"],
        "by_fault": {a: {f: [sum(v), len(v)] for f, v in fs.items()} for a, fs in by_fault.items()},
        "notes": [
            "REAL DATA REPLAY: RCAEval RE1-OB, metrics only, service-fault path only.",
            "cpu, disk and network faults are mostly outside the engine metric set; see by_fault.",
        ],
    }


def write(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
