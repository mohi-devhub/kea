"""Scenario-defined recovery: right fix, cascade healing, and live-switch safety."""

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.engine import InMemoryTopology, run_batch
from app.graph.client import load_topology
from app.main import create_app
from app.simulator.generator import generate
from app.simulator.loader import load_scenarios

RECOVER_AT_S = 150


@pytest.fixture(scope="module")
def world():  # type: ignore[no-untyped-def]
    settings = get_settings()
    topology = load_topology(settings.topology_path)
    scenarios = {s.id: s for s in load_scenarios(settings.topology_path.parent, topology)}
    return topology, scenarios


def test_events_before_recovery_are_unchanged(world) -> None:  # type: ignore[no-untyped-def]
    """A run can switch to the recovery tail mid-stream without seq or value gaps."""
    topology, scenarios = world
    scenario = scenarios["s2_postgres_degradation"]
    plain = generate(scenario, topology, 7)
    healed = generate(scenario, topology, 7, recover_at_s=RECOVER_AT_S)
    cutoff = 1_758_192_000_000 + (scenario.warmup_s + RECOVER_AT_S) * 1000
    before_plain = [e for e in plain if e.ts < cutoff]
    assert before_plain == healed[: len(before_plain)]


def test_recovery_applies_the_scenarios_own_fix(world) -> None:  # type: ignore[no-untyped-def]
    topology, scenarios = world
    s1 = generate(scenarios["s1_bad_deploy_payment"], topology, 0, recover_at_s=RECOVER_AT_S)
    rollbacks = [e for e in s1 if e.kind == "rollback"]
    assert [r.payload.deployment_id for r in rollbacks] == ["dep-182"]
    for scenario_id in ("s2_postgres_degradation", "s3_red_herring_deploy"):
        events = generate(scenarios[scenario_id], topology, 0, recover_at_s=RECOVER_AT_S)
        assert not any(e.kind == "rollback" for e in events), "must not roll back a decoy"
        assert any(e.kind == "log" and e.payload.level == "INFO" for e in events)


@pytest.mark.parametrize(
    "scenario_id",
    ["s1_bad_deploy_payment", "s2_postgres_degradation", "s3_red_herring_deploy"],
)
def test_incident_resolves_after_recovery(world, scenario_id: str) -> None:  # type: ignore[no-untyped-def]
    topology, scenarios = world
    events = generate(scenarios[scenario_id], topology, 0, recover_at_s=RECOVER_AT_S)
    incident = run_batch(events, InMemoryTopology(topology)).incident
    assert incident is not None and incident.state == "resolved"


def test_errors_use_contract_format() -> None:
    client = TestClient(create_app())  # no lifespan: validation fails before any infra is needed
    response = client.post("/events", json={"kind": "metric"})
    assert response.status_code == 422
    assert set(response.json()["error"]) == {"code", "message"}
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    ("scenario_id", "top"),
    [
        ("s1_bad_deploy_payment", "deployment:dep-182"),
        ("s2_postgres_degradation", "service_fault:postgres"),
        ("s3_red_herring_deploy", "service_fault:redis"),
    ],
)
def test_top_candidate_is_stable_while_the_root_heals(world, scenario_id: str, top: str) -> None:  # type: ignore[no-untyped-def]
    """Regression: healing the root first must not promote a downstream anomaly to root cause."""
    topology, scenarios = world
    events = generate(scenarios[scenario_id], topology, 0, recover_at_s=RECOVER_AT_S)
    incident = run_batch(events, InMemoryTopology(topology)).incident
    assert incident is not None and incident.candidates[0].candidate_id == top
