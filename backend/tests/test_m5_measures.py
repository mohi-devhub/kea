"""Measurements that back the pitch: run-to-run consistency and cost."""

import json

import pytest

from app.config import Settings
from app.eval.runner import EvalRunner
from app.graph.client import load_topology
from app.llm.fake import FakeProvider, text_response
from app.llm.models import LLMResponse
from app.simulator.loader import load_scenarios


def _answer(service: str) -> LLMResponse:
    return text_response(
        json.dumps(
            {
                "incident_detected": True,
                "ranked_hypotheses": [{"kind": "service_fault", "service": service}],
                "explanation": "x",
            }
        )
    )


async def _run(provider: FakeProvider, runs: int):  # type: ignore[no-untyped-def]
    settings = Settings(_env_file=None)
    topology = load_topology(settings.topology_path)
    scenario = next(
        s
        for s in load_scenarios(settings.topology_path.parent, topology)
        if s.id == "s2_postgres_degradation"
    )
    return await EvalRunner(settings).run(
        scenarios=[scenario], seeds=[0], approaches=["engine", "llm_raw"], runs=runs,
        baseline_provider=provider,
    )  # fmt: skip


@pytest.mark.asyncio
async def test_consistency_measures_agreement_across_repeated_runs() -> None:
    answers = [_answer("postgres")] * 4 + [_answer("payment")]
    report, _ = await _run(FakeProvider(answers), runs=5)
    row = next(r for r in report["results"] if r["approach"] == "llm_raw")
    agreement = row["extra"]["consistency"]
    assert agreement["runs_per_case"] == 5 and agreement["cases"] == 1
    assert agreement["agreement"] == pytest.approx(0.8) and agreement["unanimous_cases"] == 0


@pytest.mark.asyncio
async def test_identical_answers_are_fully_consistent_and_engine_is_deterministic() -> None:
    report, _ = await _run(FakeProvider([_answer("postgres")] * 3), runs=3)
    llm = next(r for r in report["results"] if r["approach"] == "llm_raw")
    engine = next(r for r in report["results"] if r["approach"] == "engine")
    assert llm["extra"]["consistency"]["agreement"] == 1.0
    assert engine["extra"]["determinism_rate"] == 1.0


@pytest.mark.asyncio
async def test_cost_summary_records_engine_latency_and_zero_engine_tokens() -> None:
    report, records = await _run(FakeProvider([_answer("postgres")]), runs=1)
    engine = report["cost"]["engine"]
    assert engine["median_latency_ms"] is not None and engine["median_latency_ms"] >= 0
    assert engine["median_tokens"] == 0 and engine["analyses"] == 1
    assert any(r.approach == "engine" and r.latency_ms is not None for r in records)
    assert report["cost"]["llm_raw"]["analyses"] == 1
