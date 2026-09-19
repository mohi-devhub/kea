"""Agent safety net: bad model output always ends in a grounded template, never a crash."""

import pytest

from app.agent.runner import InvestigationAgent
from app.config import get_settings
from app.engine import InMemoryTopology, run_batch
from app.graph.client import load_topology
from app.llm.fake import FakeProvider
from app.llm.models import LLMResponse, Message, ToolCall
from app.models.engine import Incident
from app.simulator.generator import generate
from app.simulator.loader import load_scenarios


def _incident() -> Incident:
    settings = get_settings()
    topology = load_topology(settings.topology_path)
    scenario = next(
        s
        for s in load_scenarios(settings.topology_path.parent, topology)
        if s.id == "s2_postgres_degradation"
    )
    incident = run_batch(generate(scenario, topology, 0), InMemoryTopology(topology)).incident
    assert incident is not None
    return incident


def _submit(**arguments: object) -> LLMResponse:
    call = ToolCall(id="c1", name="submit_investigation", arguments=dict(arguments))
    return LLMResponse(
        message=Message(role="assistant", tool_calls=[call]), finish_reason="tool_calls"
    )


def _good(incident: Incident) -> dict[str, object]:
    return {
        "summary": "Postgres degraded first.",
        "root_cause_candidate_id": incident.candidates[0].candidate_id,
        "narrative_steps": [
            {"text": "Postgres degraded first.", "evidence_ids": [incident.evidence[0].evidence_id]}
        ],
    }


@pytest.mark.asyncio
async def test_grounded_submission_is_accepted() -> None:
    incident = _incident()
    result = await InvestigationAgent().investigate(
        incident, provider=FakeProvider([_submit(**_good(incident))])
    )
    assert result.mode == "LIVE"
    assert result.root_cause_candidate_id == incident.candidates[0].candidate_id


@pytest.mark.asyncio
async def test_malformed_submission_falls_back_instead_of_crashing() -> None:
    incident = _incident()
    bad = {**_good(incident), "narrative_steps": "not a list"}
    result = await InvestigationAgent().investigate(
        incident, provider=FakeProvider([_submit(**bad)])
    )
    assert result.mode == "TEMPLATE"
    assert result.root_cause_candidate_id == incident.candidates[0].candidate_id
    assert any(entry.kind == "repair" for entry in result.trace)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"narrative_steps": [{"text": "x", "evidence_ids": ["E-9999"]}]},  # unknown evidence
        {"root_cause_candidate_id": "deployment:dep-171"},  # silent re-rank
        {"narrative_steps": [{"text": "It hit 999.0x baseline.", "evidence_ids": ["E-0001"]}]},
    ],
)
async def test_ungrounded_output_never_changes_the_ranking(change: dict[str, object]) -> None:
    incident = _incident()
    result = await InvestigationAgent().investigate(
        incident, provider=FakeProvider([_submit(**{**_good(incident), **change})])
    )
    assert result.mode == "TEMPLATE"
    assert result.root_cause_candidate_id == incident.candidates[0].candidate_id


@pytest.mark.asyncio
async def test_provider_error_uses_template() -> None:
    incident = _incident()
    result = await InvestigationAgent().investigate(incident, provider=FakeProvider([]))
    assert result.mode == "TEMPLATE"
    assert any("Provider unavailable" in caveat for caveat in result.caveats)


@pytest.mark.asyncio
async def test_unknown_tools_are_refused_not_run() -> None:
    incident = _incident()
    rogue = LLMResponse(
        message=Message(
            role="assistant", tool_calls=[ToolCall(id="t", name="rm_rf", arguments={})]
        ),
        finish_reason="tool_calls",
    )
    result = await InvestigationAgent().investigate(incident, provider=FakeProvider([rogue]))
    assert result.mode == "TEMPLATE"
    assert any(e.name == "rm_rf" and "unknown" in e.result_summary for e in result.trace)
