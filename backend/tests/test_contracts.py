"""Contract models accept the examples in docs/CONTRACTS.md and the topology file is consistent."""

from typing import Any

from pydantic import TypeAdapter

from app.config import get_settings
from app.graph.client import load_topology
from app.models.engine import Anomaly, Candidate, RejectedCandidate
from app.models.events import Event, make_event_id

EVENT: TypeAdapter[Any] = TypeAdapter(Event)


def test_metric_event_roundtrip() -> None:
    raw = {
        "schema_version": 1, "event_id": make_event_id("run-abc", 123), "run_id": "run-abc",
        "seq": 123, "ts": 1758192301000, "service": "payment", "kind": "metric",
        "payload": {"metric": "latency_p95_ms", "value": 2400.0},
    }  # fmt: skip
    assert EVENT.validate_python(raw).event_id == "run-abc:000123"


def test_unknown_metric_rejected() -> None:
    raw = {
        "event_id": "r:000001", "run_id": "r", "seq": 1, "ts": 1, "service": "payment",
        "kind": "metric", "payload": {"metric": "bogus", "value": 1.0},
    }  # fmt: skip
    try:
        EVENT.validate_python(raw)
    except ValueError:
        return
    raise AssertionError("invalid metric accepted")


def test_engine_examples() -> None:
    Anomaly.model_validate({
        "anomaly_id": "A-run-abc-0003", "run_id": "run-abc", "service": "payment",
        "metric": "latency_p95_ms", "onset_ts": 1, "detected_ts": 2, "state": "active",
        "baseline": 180.0, "peak_value": 2400.0, "ratio": 13.33,
    })  # fmt: skip
    RejectedCandidate.model_validate({
        "candidate_id": "deployment:dep-203", "service": "notifications",
        "reason_code": "NO_ANOMALY_ON_SERVICE_OR_REACHABLE", "statement": "x",
    })  # fmt: skip
    f = {"value": 0.6, "weight": 0.3, "contribution": 0.18, "explanation": "x"}
    Candidate.model_validate({
        "candidate_id": "deployment:dep-182", "kind": "deployment", "service": "payment",
        "deployment_id": "dep-182", "rank": 1, "score": 0.82, "factors": {"temporal": f},
        "root_anomaly_ids": [], "covered_anomaly_ids": [], "evidence_ids": [], "chain": [],
    })  # fmt: skip


def test_topology_consistent() -> None:
    t = load_topology(get_settings().topology_path)
    names = set(t.services)
    assert all(e.from_ in names and e.to in names for e in t.edges)
    assert set(t.metrics) == names
    assert t.customer_facing == {"web-frontend", "checkout"}
