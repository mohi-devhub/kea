"""An approach that produced no answer must never be scored as a wrong answer."""

import json
from pathlib import Path

import pytest

from app.config import Settings
from app.eval.runner import EvalRunner, write_artifacts
from app.graph.client import load_topology
from app.llm.fake import FakeProvider, text_response
from app.simulator.loader import load_scenarios
from app.simulator.models import Scenario

GOOD = json.dumps(
    {
        "incident_detected": True,
        "ranked_hypotheses": [
            {"kind": "deployment", "service": "payment", "deployment_id": "dep-182"}
        ],
        "explanation": "The payment change precedes the failure.",
    }
)


def _scenario() -> Scenario:
    settings = Settings(_env_file=None)
    topology = load_topology(settings.topology_path)
    return next(
        s
        for s in load_scenarios(settings.topology_path.parent, topology)
        if s.id == "s1_bad_deploy_payment"
    )


async def _run(provider: FakeProvider | None):  # type: ignore[no-untyped-def]
    return await EvalRunner(Settings(_env_file=None)).run(
        scenarios=[_scenario()],
        seeds=[0],
        approaches=["engine", "llm_raw"],
        baseline_provider=provider,
    )


def _row(report: dict, approach: str) -> dict:  # type: ignore[type-arg]
    return next(r for r in report["results"] if r["approach"] == approach)


@pytest.mark.asyncio
async def test_baseline_that_did_not_run_is_reported_as_not_run(tmp_path: Path) -> None:
    report, records = await _run(None)
    row = _row(report, "llm_raw")
    assert row["n"] == 0 and row["unscored"] == {"not_run": 1}
    assert any("llm_raw: no answers were produced" in w for w in report["warnings"])
    write_artifacts(report, records, tmp_path)
    markdown = (tmp_path / "report.md").read_text()
    row_line = next(line for line in markdown.splitlines() if line.startswith("| llm_raw"))
    assert "not run" in row_line and "0/1" not in row_line and "Read this first" in markdown
    assert _row(report, "engine")["n"] == 1  # the engine still scores normally


@pytest.mark.asyncio
async def test_provider_error_is_unscored_and_not_retried_as_a_repair() -> None:
    provider = FakeProvider([])  # raises LLMError on the first call
    report, records = await _run(provider)
    assert len(provider.requests) == 1  # no "repair" retry for an infrastructure failure
    assert _row(report, "llm_raw")["unscored"] == {"provider_error": 1}
    baseline = next(r for r in records if r.approach == "llm_raw")
    assert baseline.status == "provider_error" and baseline.error


@pytest.mark.asyncio
async def test_parse_failure_is_scored_incorrect_and_disclosed() -> None:
    provider = FakeProvider([text_response("not json"), text_response("still not json")])
    report, _ = await _run(provider)
    row = _row(report, "llm_raw")
    assert row["n"] == 1 and row["top1_correct"]["k"] == 0 and row["parse_errors"] == 1
    assert row["unscored"] == {}
    assert len(provider.requests) == 2  # one repair attempt, then it counts against the baseline


@pytest.mark.asyncio
async def test_valid_answer_is_scored_normally_and_meta_is_truthful() -> None:
    provider = FakeProvider([text_response(GOOD)], model="model-under-test")
    report, _ = await _run(provider)
    row = _row(report, "llm_raw")
    assert row["n"] == 1 and row["top1_correct"]["k"] == 1 and not report["warnings"]
    meta = report["meta"]
    assert meta["baseline_model"] == "model-under-test" and meta["agent_model"] is None
    assert list(report["engine_config"]["weights"]) == [0.30, 0.35, 0.15, 0.20]


def test_metric_window_starts_before_the_fault_so_onset_order_is_visible() -> None:
    """Regression: a 'last 120 s' window hid the root cause's onset in slow scenarios."""
    from app.eval.baselines.render import render_baseline_input
    from app.simulator.generator import EPOCH_MS, generate

    settings = Settings(_env_file=None)
    topology = load_topology(settings.topology_path)
    scenario = next(
        s
        for s in load_scenarios(settings.topology_path.parent, topology)
        if s.id == "s2_postgres_degradation"
    )
    events = generate(scenario, topology, 0)
    start = EPOCH_MS + (scenario.warmup_s - 120) * 1000
    text = render_baseline_input(events, topology=topology, metric_window_start=start)
    first = text[text.index("window: ") + 8 : text.index(" .. analysis")]
    fault_time = (scenario.warmup_s - 120) % 86_400  # seconds after the epoch's midnight clock
    assert first.count(":") == 2 and fault_time >= 0
    # the postgres latency series must include a bucket from before the fault (healthy baseline)
    series = text[text.index("service: postgres | metric: latency_p95_ms") :].splitlines()[1]
    assert series.strip().startswith(first)
