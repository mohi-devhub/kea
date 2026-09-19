"""M1 acceptance tests: scenarios are data, engine results are deterministic."""
# ruff: noqa: E501

import hashlib
import json

import pytest

from app.config import get_settings
from app.engine import EngineState, InMemoryTopology, run_batch
from app.graph.client import load_topology
from app.models.events import MetricEvent, make_event_id
from app.simulator.generator import generate
from app.simulator.loader import load_scenarios


@pytest.fixture(scope="module")
def scenarios():  # type: ignore[no-untyped-def]
    settings = get_settings()
    return load_scenarios(settings.topology_path.parent, load_topology(settings.topology_path))


def test_generator_is_deterministic(scenarios) -> None:  # type: ignore[no-untyped-def]
    topology = load_topology(get_settings().topology_path)
    scenario = scenarios[0]
    first = [event.model_dump(mode="json") for event in generate(scenario, topology, 3)]
    second = [event.model_dump(mode="json") for event in generate(scenario, topology, 3)]
    assert (
        hashlib.sha256(json.dumps(first, sort_keys=True).encode()).digest()
        == hashlib.sha256(json.dumps(second, sort_keys=True).encode()).digest()
    )


def test_generated_events_have_stable_ids_and_monotonic_time(scenarios) -> None:  # type: ignore[no-untyped-def]
    topology = load_topology(get_settings().topology_path)
    events = generate(scenarios[0], topology, 0)
    assert [event.seq for event in events] == list(range(len(events)))
    assert len({event.event_id for event in events}) == len(events)
    assert [event.ts for event in events] == sorted(event.ts for event in events)


@pytest.mark.parametrize("seed", range(5))
def test_scenario_matrix(scenarios, seed: int) -> None:  # type: ignore[no-untyped-def]
    topology = load_topology(get_settings().topology_path)
    for scenario in scenarios:
        result = run_batch(generate(scenario, topology, seed), InMemoryTopology(topology))
        truth = scenario.ground_truth
        assert result.incident_open is truth.expect_incident, scenario.id
        if not truth.expect_incident:
            continue
        assert truth.root_cause is not None
        expected = (
            f"{truth.root_cause.kind}:{truth.root_cause.deployment_id or truth.root_cause.service}"
        )
        assert result.candidates[0].candidate_id == expected, scenario.id
        assert all(
            candidate.service not in truth.must_not_implicate for candidate in result.candidates[:1]
        )
        actual_rejections = {
            item.candidate_id: item.reason_code for item in result.rejected_candidates
        }
        for expected_rejection in truth.must_reject:
            assert (
                actual_rejections.get(expected_rejection.candidate_id)
                == expected_rejection.reason_code
            )


def test_batch_equals_incremental(scenarios) -> None:  # type: ignore[no-untyped-def]
    topology = load_topology(get_settings().topology_path)
    events = generate(scenarios[0], topology, 0)
    first = run_batch(events, InMemoryTopology(topology))
    state = EngineState(events[0].run_id, InMemoryTopology(topology))
    for event in events:
        state.ingest(event)
    assert first == state.result()


def test_candidates_expose_complete_factor_breakdown(scenarios) -> None:  # type: ignore[no-untyped-def]
    topology = load_topology(get_settings().topology_path)
    result = run_batch(generate(scenarios[0], topology, 0), InMemoryTopology(topology))
    candidate = result.candidates[0]
    assert set(candidate.factors) == {
        "temporal",
        "dependency_consistency",
        "anomaly_strength",
        "downstream_impact",
    }
    total = sum(factor.contribution for factor in candidate.factors.values())
    assert abs(total - candidate.score) < 1e-4


def test_incident_has_evidence_chain_and_what_changed(scenarios) -> None:  # type: ignore[no-untyped-def]
    topology = load_topology(get_settings().topology_path)
    result = run_batch(generate(scenarios[0], topology, 0), InMemoryTopology(topology))
    assert result.incident is not None
    assert result.incident.evidence
    assert result.incident.what_changed.changes
    assert result.incident.candidates[0].chain[0].node_type == "deployment"
    assert result.incident.candidates[0].evidence_ids


def test_resolution_restores_health_and_closes_incident() -> None:
    topology = load_topology(get_settings().topology_path)
    state = EngineState("resolution", InMemoryTopology(topology))
    events: list[MetricEvent] = []
    for tick in range(12):
        for service in ("payment", "checkout"):
            events.append(_metric("resolution", len(events), tick * 5_000, service, 100.0))
    for tick in range(12, 15):
        for service in ("payment", "checkout"):
            events.append(_metric("resolution", len(events), tick * 5_000, service, 300.0))
    for tick in range(15, 25):
        for service in ("payment", "checkout"):
            events.append(_metric("resolution", len(events), tick * 5_000, service, 100.0))
    for event in events:
        state.ingest(event)
    assert state.service_health["payment"] == "healthy"
    assert state.incident is not None
    assert state.incident.state == "resolved"
    assert any(update.type == "incident_resolved" for update in state.updates)


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
