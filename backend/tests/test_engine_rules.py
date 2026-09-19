"""Focused M1 engine rules that are not fully exercised by the scenario matrix."""

import ast
from pathlib import Path

from app.config import get_settings
from app.engine import EngineState, InMemoryTopology
from app.engine.core import Deployment
from app.graph.client import load_topology
from app.models.engine import Anomaly
from app.models.events import MetricEvent, make_event_id


def test_single_spike_does_not_create_anomaly() -> None:
    topology = load_topology(get_settings().topology_path)
    state = EngineState("spike", InMemoryTopology(topology))
    values = [100.0] * 12 + [300.0] + [100.0] * 3
    for index, value in enumerate(values):
        state.ingest(_metric("spike", index, index * 5_000, "payment", value))
    assert state.anomalies == []


def test_single_service_anomaly_enters_pending_watch() -> None:
    topology = load_topology(get_settings().topology_path)
    state = EngineState("pending", InMemoryTopology(topology))
    values = [100.0] * 12 + [300.0] * 3
    for index, value in enumerate(values):
        state.ingest(_metric("pending", index, index * 5_000, "payment", value))
    assert state.incident is None
    assert any(update.type == "pending_watch" for update in state.updates)


def test_all_rejection_reason_codes_are_reachable() -> None:
    topology = load_topology(get_settings().topology_path)
    state = EngineState("rejections", InMemoryTopology(topology))
    deployment = Deployment("dep", "payment", 0)
    anomaly = _anomaly("A-1", "payment", 10_000)
    assert (
        state._rejection_reason(deployment, [], [], 10_000) == "NO_ANOMALY_ON_SERVICE_OR_REACHABLE"
    )
    assert (
        state._rejection_reason(deployment, [anomaly], [], 10_000)
        == "ANOMALY_EXPLAINED_BY_EARLIER_CAUSE"
    )
    later_deployment = Deployment("later", "payment", 20_000)
    assert (
        state._rejection_reason(later_deployment, [anomaly], [anomaly], 10_000)
        == "ANOMALY_PRECEDES_DEPLOYMENT"
    )
    old_deployment = Deployment("old", "payment", 0)
    old_anomaly = _anomaly("A-2", "payment", 300_000)
    assert (
        state._rejection_reason(old_deployment, [old_anomaly], [old_anomaly], 300_000)
        == "OUTSIDE_LOOKBACK_WINDOW"
    )


def test_engine_has_no_forbidden_layer_imports_or_clock_calls() -> None:
    engine_dir = Path(__file__).resolve().parents[1] / "app" / "engine"
    forbidden = {"simulator", "eval", "agent", "llm", "stream", "graph", "api"}
    for path in engine_dir.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                parts = node.module.split(".")
                assert parts[0] not in forbidden
                assert not (len(parts) > 1 and parts[0] == "app" and parts[1] in forbidden)
            if isinstance(node, ast.Attribute):
                assert not (
                    isinstance(node.value, ast.Name)
                    and node.value.id in {"time", "datetime"}
                    and node.attr in {"time", "now"}
                )


def _metric(run_id: str, seq: int, ts: int, service: str, value: float) -> MetricEvent:
    return MetricEvent(
        event_id=make_event_id(run_id, seq),
        run_id=run_id,
        seq=seq,
        ts=ts,
        service=service,
        kind="metric",
        payload={"metric": "latency_p95_ms", "value": value},
    )


def _anomaly(anomaly_id: str, service: str, onset_ts: int) -> Anomaly:
    return Anomaly(
        anomaly_id=anomaly_id,
        run_id="rejections",
        service=service,
        metric="latency_p95_ms",
        onset_ts=onset_ts,
        detected_ts=onset_ts + 10_000,
        state="active",
        baseline=100.0,
        peak_value=300.0,
        ratio=3.0,
    )
