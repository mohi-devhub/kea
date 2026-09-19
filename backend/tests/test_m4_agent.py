"""M4 agent contracts: deterministic output, tool safety, and grounding."""

from pathlib import Path

import pytest

from app.agent.grounding import validate_grounding
from app.agent.runner import InvestigationAgent
from app.agent.templates import build_template_investigation
from app.agent.tools import ToolContext
from app.api.store import RunView
from app.config import get_settings
from app.engine import InMemoryTopology, run_batch
from app.graph.client import load_topology
from app.llm.cache import CachedProvider
from app.llm.fake import FakeProvider
from app.llm.models import LLMResponse, Message, ToolCall
from app.simulator.generator import generate
from app.simulator.loader import load_scenarios


def _incident(scenario_id: str):  # type: ignore[no-untyped-def]
    settings = get_settings()
    topology = load_topology(settings.topology_path)
    scenario = next(
        item
        for item in load_scenarios(settings.topology_path.parent, topology)
        if item.id == scenario_id
    )
    incident = run_batch(generate(scenario, topology, 0), InMemoryTopology(topology)).incident
    assert incident is not None
    return incident, topology


@pytest.mark.parametrize(
    "scenario_id",
    ["s1_bad_deploy_payment", "s2_postgres_degradation", "s3_red_herring_deploy"],
)
def test_template_investigation_is_grounded_for_all_m3_scenarios(scenario_id: str) -> None:
    incident, _ = _incident(scenario_id)
    result = build_template_investigation(incident, "INV-test")
    assert result.mode == "TEMPLATE"
    assert result.root_cause_candidate_id == incident.candidates[0].candidate_id
    assert 1 <= len(result.narrative_steps) <= 8
    assert not validate_grounding(result, incident)
    known = {item.evidence_id for item in incident.evidence}
    assert all(set(step.evidence_ids) <= known for step in result.narrative_steps)


@pytest.mark.asyncio
async def test_fake_provider_can_submit_a_grounded_investigation() -> None:
    incident, topology = _incident("s1_bad_deploy_payment")
    provider = FakeProvider(
        [
            LLMResponse(
                message=Message(
                    role="assistant",
                    tool_calls=[
                        ToolCall(
                            id="submit-1",
                            name="submit_investigation",
                            arguments={
                                "summary": (
                                    "The payment deployment is the leading engine candidate."
                                ),
                                "root_cause_candidate_id": incident.candidates[0].candidate_id,
                                "narrative_steps": [
                                    {
                                        "text": incident.candidates[0].chain[0].statement,
                                        "evidence_ids": [incident.candidates[0].evidence_ids[0]],
                                    }
                                ],
                            },
                        )
                    ],
                )
            )
        ]
    )
    # Tool execution is part of the same bounded loop even when the model submits
    # immediately; this also proves the context exposes only read-only handlers.
    context = ToolContext(RunView(incident.run_id, incident=incident), topology)
    result = await InvestigationAgent().investigate(
        incident, provider=provider, tool_context=context
    )
    assert result.mode == "LIVE"
    assert result.root_cause_candidate_id == incident.candidates[0].candidate_id
    assert not validate_grounding(result, incident)
    assert any(item.kind == "model" for item in result.trace)


def test_agent_tools_are_explicitly_read_only() -> None:
    incident, topology = _incident("s1_bad_deploy_payment")
    context = ToolContext(RunView(incident.run_id, incident=incident), topology)
    registry = context.registry()
    assert registry
    assert all(tool.read_only for tool in registry.values())
    assert "submit_investigation" not in registry


@pytest.mark.asyncio
async def test_record_replay_cache_uses_same_response(tmp_path: Path) -> None:
    from app.llm.models import LLMRequest

    request = LLMRequest(model="fake-v1", messages=[Message(role="user", content="hello")])
    live = FakeProvider(
        [
            LLMResponse(
                message=Message(role="assistant", content="cached"),
                provider="fake",
                model="fake-v1",
            )
        ]
    )
    recorder = CachedProvider(live, tmp_path, "record")
    first = await recorder.generate(request)
    replay = CachedProvider(FakeProvider(), tmp_path, "replay")
    second = await replay.generate(request)
    assert first == second
