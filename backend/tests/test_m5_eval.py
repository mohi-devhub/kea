"""M5 acceptance tests for fair rendering, grading, statistics, and the runner."""

import ast
import json
from pathlib import Path

import pytest

from app.config import Settings
from app.eval.baselines.parser import parse_output
from app.eval.baselines.render import render_baseline_input
from app.eval.metrics import wilson_interval
from app.eval.runner import EvalRunner, write_artifacts
from app.graph.client import load_topology
from app.llm.fake import FakeProvider
from app.llm.models import LLMResponse, Message
from app.simulator.generator import generate
from app.simulator.loader import load_scenarios


def _scenario(scenario_id: str):  # type: ignore[no-untyped-def]
    settings = Settings(_env_file=None)
    topology = load_topology(settings.topology_path)
    scenario = next(
        item
        for item in load_scenarios(settings.topology_path.parent, topology)
        if item.id == scenario_id
    )
    return scenario, topology


def test_baseline_render_has_no_engine_or_truth_leakage() -> None:
    scenario, topology = _scenario("s1_bad_deploy_payment")
    events = generate(scenario, topology, 0)
    rendered = render_baseline_input(events, topology=topology, include_topology=True)
    forbidden = {
        scenario.id,
        "ground_truth",
        "decoy",
        scenario.ground_truth.root_cause.model_dump_json()
        if scenario.ground_truth.root_cause
        else "",
    }
    assert all(value not in rendered for value in forbidden if value)
    assert "deployment:dep-182" not in rendered
    assert "E-0001" not in rendered
    assert "DEPLOYMENTS AND ROLLBACKS" in rendered
    assert "TOPOLOGY" in rendered


def test_baseline_package_does_not_import_simulator() -> None:
    root = Path(__file__).parents[1] / "app" / "eval" / "baselines"
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        assert not any(module.startswith("app.simulator") for module in imports), path


def test_parser_rejects_invalid_output_and_accepts_fenced_json() -> None:
    parsed = parse_output(
        '```json\n{"incident_detected": false, "ranked_hypotheses": [], "explanation": "none"}\n```'
    )
    assert parsed.incident_detected is False
    with pytest.raises((ValueError, json.JSONDecodeError)):
        parse_output("not json")
    with pytest.raises(ValueError):
        parse_output('{"incident_detected": false, "unexpected": true}')


def test_wilson_interval_known_values() -> None:
    interval = wilson_interval(5, 10)
    assert interval.k == 5 and interval.n == 10
    assert round(interval.ci_low, 3) == 0.237
    assert round(interval.ci_high, 3) == 0.763


@pytest.mark.asyncio
async def test_runner_completes_with_fake_provider_and_template_hybrid(tmp_path: Path) -> None:
    scenario, _ = _scenario("s1_bad_deploy_payment")
    provider = FakeProvider(
        [
            LLMResponse(
                message=Message(
                    role="assistant",
                    content=json.dumps(
                        {
                            "incident_detected": True,
                            "ranked_hypotheses": [
                                {
                                    "kind": "deployment",
                                    "service": "payment",
                                    "deployment_id": "dep-182",
                                }
                            ],
                            "explanation": "The payment change precedes the failure.",
                        }
                    ),
                )
            )
        ]
    )
    runner = EvalRunner(Settings(_env_file=None))
    report, records = await runner.run(
        scenarios=[scenario],
        seeds=[0],
        approaches=["engine", "llm_raw", "hybrid"],
        baseline_provider=provider,
    )
    assert len(records) == 3
    assert next(item for item in records if item.approach == "engine").grade.top1_correct
    assert next(item for item in records if item.approach == "llm_raw").grade.top1_correct
    hybrid = next(item for item in records if item.approach == "hybrid")
    assert hybrid.grade.mode == "TEMPLATE"
    assert report["results"]
    write_artifacts(report, records, tmp_path / "report")
    assert (tmp_path / "report" / "report.json").exists()
    assert (tmp_path / "report" / "report.md").exists()
    assert len((tmp_path / "report" / "runs.jsonl").read_text().splitlines()) == 3
