"""Explanations, evidence and What-changed text must be specific enough to trace (UI, agent)."""

import re

from app.config import get_settings
from app.engine import InMemoryTopology, run_batch
from app.graph.client import load_topology
from app.simulator.generator import generate
from app.simulator.loader import load_scenarios


def _incident(scenario_id: str):  # type: ignore[no-untyped-def]
    settings = get_settings()
    topology = load_topology(settings.topology_path)
    scenario = next(
        s for s in load_scenarios(settings.topology_path.parent, topology) if s.id == scenario_id
    )
    incident = run_batch(generate(scenario, topology, 0), InMemoryTopology(topology)).incident
    assert incident is not None
    return incident


def test_factor_explanations_are_specific() -> None:
    incident = _incident("s1_bad_deploy_payment")
    top = incident.candidates[0]
    assert "dep-182" in top.factors["temporal"].explanation
    assert "incident anomalies are explained" in top.factors["dependency_consistency"].explanation
    assert "x baseline" in top.factors["anomaly_strength"].explanation
    assert "customer-facing" in top.factors["downstream_impact"].explanation


def test_evidence_ids_are_per_candidate_and_resolvable() -> None:
    incident = _incident("s2_postgres_degradation")
    known = {e.evidence_id for e in incident.evidence}
    for candidate in incident.candidates:
        assert candidate.evidence_ids and set(candidate.evidence_ids) <= known
    rejected_ref = incident.rejected_candidates[0].candidate_id
    assert rejected_ref not in {c.candidate_id for c in incident.candidates}
    assert any(e.ref == rejected_ref for e in incident.evidence)


def test_what_changed_statement_is_readable() -> None:
    statement = _incident("s3_red_herring_deploy").what_changed.statement
    assert re.search(r"healthy until \d\d:\d\d:\d\d", statement)
    assert "dep-203" in statement and "rejected" in statement
    assert not re.search(r"\d{10,}", statement)  # no raw epoch timestamps
