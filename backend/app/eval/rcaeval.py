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

from app.config import ROOT
from app.eval.metrics import aggregate_records, cost_summary
from app.eval.models import RunRecord
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
SPLIT_PATH = ROOT / "eval_results" / "rcaeval_split.json"
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


def split_case_names(split: str, path: Path = SPLIT_PATH) -> list[str]:
    """Read the frozen case list; no split may be inferred from measured results."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if split not in {"tune", "test"}:
        raise ValueError("split must be tune or test")
    cases = value.get(split)
    if not isinstance(cases, list) or not all(isinstance(item, str) for item in cases):
        raise ValueError(f"frozen RCAEval split is missing {split}")
    if len(cases) != len(set(cases)):
        raise ValueError(f"frozen RCAEval {split} split contains duplicate cases")
    return list(cases)


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
    columns: dict[str, dict[str, list[float | None]]] = {}
    for column, values in table.items():
        service, _, raw = column.partition("_")
        if service in topology.services:
            columns.setdefault(service, {})[raw] = values

    def pre_median(values: list[float | None]) -> float | None:
        normal = [v for v, t in zip(values, times, strict=True) if t < inject and v is not None]
        return median(normal) if normal else None

    mapped: list[tuple[str, str, list[float | None]]] = []
    for service in sorted(columns):
        raw_columns = columns[service]
        for raw, values in sorted(raw_columns.items()):
            if raw == "mem":
                baseline = pre_median(values)
                if baseline is None or baseline == 0:
                    continue
                series = [100 * v / (2 * baseline) if v is not None else None for v in values]
                mapped.append((service, "memory_used_pct", series))
            elif raw == "cpu":
                mapped.append((service, "cpu_pct", values))
            elif raw in _METRIC:
                scale = 1000 if raw == "latency-90" else 1
                series = [v * scale if v is not None else None for v in values]
                mapped.append((service, _METRIC[raw], series))
            elif raw == "socket":
                baseline = pre_median(values)
                if baseline is None:
                    continue
                series = [
                    max(0.0, 100 * (v - baseline) / max(baseline, 1.0)) if v is not None else None
                    for v in values
                ]
                mapped.append((service, "packet_loss_pct", series))
        p50 = raw_columns.get("latency-50")
        p90 = raw_columns.get("latency-90")
        if p50 is not None and p90 is not None:
            series = [
                max(0.0, (hi - lo) * 1000) if hi is not None and lo is not None else None
                for lo, hi in zip(p50, p90, strict=True)
            ]
            mapped.append((service, "network_delay_ms", series))

    events: list[Event] = []
    for service, metric, series in mapped:
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
        id=case, title=case, description="RCAEval real fault injection", priority="P1",
        warmup_s=warmup, duration_s=times[-1] - inject, deployments=[], effects=[],
        ground_truth=GroundTruth(
            expect_incident=True, root_cause=RootCause(kind="service_fault", service=service),
            must_not_implicate=[], must_reject=[], ordering_constraints=[],
        ),
    )  # fmt: skip
    return events, scenario


async def run_rcaeval(
    runner: EvalRunner,
    cache: Path,
    cases: list[str],
    approaches: list[str],
    *,
    split: str | None = None,
    **providers: Any,
) -> dict[str, Any]:
    loaded = {c: load_case(c, fetch(c, cache), topology_for_case(c)) for c in cases}
    records: list[RunRecord] = []
    topology_names = {"sock_shop" if c.startswith("re1ss_") else "online_boutique" for c in cases}
    for topology_name in sorted(topology_names):
        group = [c for c in cases if c.startswith("re1ss_") == (topology_name == "sock_shop")]
        runner.topology = sock_shop() if topology_name == "sock_shop" else online_boutique()
        report, group_records = await runner.run(
            scenarios=[loaded[c][1] for c in group],
            seeds=[0],
            approaches=approaches,
            events_for=lambda scenario, _seed: loaded[scenario.id][0],
            **providers,
        )
        records.extend(group_records)
    aggregates = [item.model_dump(mode="json") for item in aggregate_records(records)]
    by_fault: dict[str, dict[str, list[int]]] = {}
    by_fault_top3: dict[str, dict[str, list[int]]] = {}
    for row in aggregates:
        fault = row["scenario"].split("_")[2]
        bucket = by_fault.setdefault(row["approach"], {}).setdefault(fault, [0, 0])
        bucket[0] += row["top1_correct"]["k"]
        bucket[1] += row["n"]
        top3_bucket = by_fault_top3.setdefault(row["approach"], {}).setdefault(fault, [0, 0])
        top3_bucket[0] += row["top3_contains"]["k"]
        top3_bucket[1] += row["n"]
    weights_path = Path(__file__).with_name("learned_weights_v1.json")
    weights_payload = (
        json.loads(weights_path.read_text(encoding="utf-8")) if weights_path.exists() else {}
    )
    unscored = sorted(
        {row["approach"] for row in aggregates if row.get("n", 0) == 0 and row.get("unscored")}
    )
    notes = [
        f"REAL DATA REPLAY: RCAEval {split or 'custom'} split, metrics only, "
        "service-fault path only.",
        "CPU and latency-tail network signals are mapped; disk remains unmapped and the "
        "packet-loss metric is a socket-count proxy where available.",
    ]
    if unscored:
        notes.append(
            "Unscored approaches (no provider answer) are excluded from accuracy denominators: "
            + ", ".join(unscored)
            + "."
        )
    return {
        "cases": len(cases),
        "split": split,
        "results": aggregates,
        "cost": cost_summary(records),
        "by_fault": by_fault,
        "by_fault_top3": by_fault_top3,
        "learning": {
            "weights_version": weights_payload.get("version"),
            "training": weights_payload.get("training_metadata"),
            "evaluation_split": split,
        },
        "notes": notes,
    }


def write(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
