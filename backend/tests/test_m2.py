"""M2 stream, worker, and materialized-view tests without external services."""

import pytest

from app.api.store import RunStore
from app.config import get_settings
from app.engine.prediction import make_prediction, verify_prediction
from app.models.engine import Anomaly, BlastRadius, Candidate, Incident, WhatChanged
from app.models.events import MetricEvent, make_event_id
from app.stream.worker import Worker


def _event(run_id: str, seq: int, value: float) -> dict[str, object]:
    return {
        "schema_version": 1,
        "event_id": make_event_id(run_id, seq),
        "run_id": run_id,
        "seq": seq,
        "ts": seq * 5_000,
        "service": "payment",
        "kind": "metric",
        "payload": {"metric": "latency_p95_ms", "value": value},
    }


@pytest.mark.asyncio
async def test_worker_deduplicates_and_drops_invalid_events() -> None:
    worker = Worker("unused", str(get_settings().topology_path))
    assert await worker.handle(_event("run", 1, 100.0)) == []
    assert await worker.handle(_event("run", 1, 100.0)) == []
    assert worker.duplicate_events == 1
    assert await worker.handle({"kind": "metric", "service": "unknown"}) == []
    assert worker.invalid_events == 1


@pytest.mark.asyncio
async def test_run_store_snapshot_and_metrics() -> None:
    store = RunStore()
    store.create("run", "s1_bad_deploy_payment", 42, 10)
    event = MetricEvent.model_validate(_event("run", 1, 123.0))
    store.record_event(event)
    queue = await store.subscribe()
    await store.update(
        {
            "run_id": "run",
            "seq": 2,
            "sim_ts": 10_000,
            "type": "service_health_changed",
            "payload": {"service": "payment", "health": "degraded"},
        }
    )
    assert (await queue.get())["type"] == "service.health"
    await store.broadcast(
        {"type": "metrics.batch", "run_id": "run", "seq": 1, "sim_ts": 5_000, "payload": []}
    )
    assert (await queue.get())["type"] == "metrics.batch"
    snapshot = store.snapshot()
    assert snapshot["type"] == "snapshot"
    assert snapshot["payload"]["runs"][0]["run_id"] == "run"
    assert store.runs["run"].metrics[("payment", "latency_p95_ms")][0]["value"] == 123.0
    store.unsubscribe(queue)


def test_prediction_is_frozen_and_verifiable() -> None:
    incident = Incident.model_construct(
        incident_id="INC-1",
        run_id="run",
        state="open",
        revision=3,
        opened_ts=100,
        first_anomaly_ts=100,
        resolved_ts=None,
        anomalies=[
            Anomaly(
                anomaly_id="A-1",
                run_id="run",
                service="payment",
                metric="latency_p95_ms",
                onset_ts=100,
                detected_ts=110,
                state="active",
                baseline=100,
                peak_value=300,
                ratio=3,
            )
        ],
        service_health={"payment": "failing", "checkout": "healthy"},
        candidates=[
            Candidate.model_construct(
                candidate_id="service_fault:payment",
                kind="service_fault",
                service="payment",
                deployment_id=None,
                rank=1,
                score=1,
                factors={},
                root_anomaly_ids=["A-1"],
                covered_anomaly_ids=["A-1"],
                evidence_ids=[],
                chain=[],
            )
        ],
        rejected_candidates=[],
        ambiguous=False,
        margin=1,
        what_changed=WhatChanged(
            healthy_until_ts=0, first_anomaly_ts=100, changes=[], statement=""
        ),
        blast_radius=BlastRadius(customer_facing_affected=[], services=["payment"]),
        evidence=[],
    )
    prediction = make_prediction(incident, 120)
    assert prediction.predicted_healed == ["payment"]
    verification = verify_prediction(prediction, {"payment": "healthy", "checkout": "healthy"}, 200)
    assert verification.verdict == "confirmed"
