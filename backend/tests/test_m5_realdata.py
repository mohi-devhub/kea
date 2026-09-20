import json

import pytest

from app.config import Settings
from app.engine import InMemoryTopology, run_batch
from app.engine.config import EngineConfig
from app.eval.rcaeval import online_boutique
from app.eval.runner import EvalRunner
from app.graph.client import load_topology
from app.llm.fake import FakeProvider, text_response
from app.models.events import MetricEvent
from app.simulator.generator import EPOCH_MS, generate
from app.simulator.loader import load_scenarios


def _series(metric: str, values: list[float]) -> list[MetricEvent]:
    return [
        MetricEvent(
            kind="metric",
            event_id=f"realdata:{metric}:{index}",
            run_id="realdata",
            seq=index,
            ts=EPOCH_MS + index * 5_000,
            service="frontend",
            payload={"metric": metric, "value": value},
        )
        for index, value in enumerate(values)
    ]


def test_step1_cpu_network_and_packet_loss_metrics_detect() -> None:
    values = [20.0] * 15 + [80.0] * 3
    events = _series("cpu_pct", values)
    events += _series("network_delay_ms", [5.0] * 15 + [40.0] * 3)
    events += _series("packet_loss_pct", [0.0] * 15 + [5.0] * 3)
    events.sort(key=lambda event: (event.ts, event.payload.metric))

    result = run_batch(events, InMemoryTopology(online_boutique()))

    assert {anomaly.metric for anomaly in result.anomalies} == {
        "cpu_pct",
        "network_delay_ms",
        "packet_loss_pct",
    }


def test_step2_robust_mad_rejects_noisy_spikes_and_detects_step() -> None:
    noisy = [70.0, 130.0] * 8 + [300.0] * 3
    old = run_batch(
        _series("cpu_pct", noisy),
        InMemoryTopology(online_boutique()),
        EngineConfig(use_robust_baseline=False, cpu_delta_pts=0.0, cpu_ratio=1.5),
    )
    robust = run_batch(
        _series("cpu_pct", noisy + [1000.0] * 3),
        InMemoryTopology(online_boutique()),
        EngineConfig(cpu_delta_pts=0.0, cpu_ratio=1.5, cpu_mad_sensitivity=8.0),
    )

    assert any(anomaly.metric == "cpu_pct" for anomaly in old.anomalies)
    assert len(robust.anomalies) == 1
    assert robust.anomalies[0].peak_value == 1000.0


def test_step3_onset_uses_persistence_timestamp() -> None:
    result = run_batch(
        _series("cpu_pct", [20.0] * 15 + [80.0] * 3),
        InMemoryTopology(online_boutique()),
    )

    assert result.anomalies[0].onset_ts == EPOCH_MS + 17 * 5_000


def _scenario(scenario_id: str):  # type: ignore[no-untyped-def]
    settings = Settings(_env_file=None)
    topology = load_topology(settings.topology_path)
    scenario = next(
        item
        for item in load_scenarios(settings.topology_path.parent, topology)
        if item.id == scenario_id
    )
    return scenario, topology


@pytest.mark.asyncio
async def test_step4_reranker_can_only_permute_engine_candidates() -> None:
    scenario, topology = _scenario("s1_bad_deploy_payment")
    events = generate(scenario, topology, 0)
    engine_result = run_batch(events, InMemoryTopology(topology))
    original = [item.candidate_id for item in engine_result.candidates[:3]]
    provider = FakeProvider(
        [
            text_response(
                json.dumps(
                    {
                        "ordered_candidate_ids": list(reversed(original)),
                        "evidence_ids": engine_result.candidates[0].evidence_ids[:1],
                        "explanation": "The supplied evidence supports this order.",
                    }
                )
            )
        ]
    )
    report, records = await EvalRunner(Settings(_env_file=None)).run(
        scenarios=[scenario],
        seeds=[0],
        approaches=["hybrid_rerank"],
        agent_provider=provider,
    )
    record = records[0]
    assert record.status == "ok"
    assert record.parsed_output["original_candidate_ids"] == original
    assert record.parsed_output["reranked_candidate_ids"] == list(reversed(original))
    assert record.grade.grounding_pass is True
    assert len(provider.requests) == 1
    assert scenario.id not in provider.requests[0].messages[1].content
    assert report["cost"]["hybrid_rerank"]["total_tokens"] == 0


@pytest.mark.asyncio
async def test_step4_malformed_rerank_falls_back_to_engine_order() -> None:
    scenario, _ = _scenario("s1_bad_deploy_payment")
    provider = FakeProvider([text_response("not json")])
    _, records = await EvalRunner(Settings(_env_file=None)).run(
        scenarios=[scenario],
        seeds=[0],
        approaches=["hybrid_rerank"],
        agent_provider=provider,
    )
    record = records[0]
    assert record.status == "parse_error"
    assert record.grade.top1_correct is True
    assert (
        record.grade.details["original_candidate_ids"]
        == record.grade.details["reranked_candidate_ids"]
    )
    assert record.grade.details["fallback"] is True


@pytest.mark.asyncio
async def test_step4_no_incident_skips_provider_and_preserves_no_alarm() -> None:
    scenario, _ = _scenario("s4_benign_deploy")
    provider = FakeProvider([])
    _, records = await EvalRunner(Settings(_env_file=None)).run(
        scenarios=[scenario],
        seeds=[0],
        approaches=["hybrid_rerank"],
        agent_provider=provider,
    )
    record = records[0]
    assert not provider.requests
    assert record.status == "ok"
    assert record.grade.top1_correct is True
    assert record.grade.false_alarm is False
