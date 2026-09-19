"""Deterministic evaluation runner with offline-safe template and FakeProvider paths."""

import hashlib
import json
import subprocess
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.agent.runner import InvestigationAgent
from app.config import ROOT, Settings, get_settings
from app.engine import EngineState, InMemoryTopology, run_batch
from app.engine.config import EngineConfig
from app.eval.baselines.parser import parse_output
from app.eval.baselines.prompts import BASELINE_PROMPT_VERSION, SYSTEM_PROMPT, build_prompt
from app.eval.baselines.render import render_baseline_input
from app.eval.grading import grade_baseline, grade_engine, grade_hybrid
from app.eval.metrics import aggregate_records
from app.eval.models import BaselineAnswer, Grade, RunRecord, RunStatus
from app.graph.client import load_topology
from app.llm.base import LLMProvider
from app.llm.models import LLMRequest, Message
from app.models.engine import Incident
from app.simulator.generator import EPOCH_MS, generate
from app.simulator.loader import load_scenarios

DEFAULT_HELDOUT = list(range(100, 110))
DEFAULT_TUNING = list(range(0, 5))
LIMITATIONS = [
    "Scenarios are authored by the same team that built the engine; held-out seeds vary timing, "
    "noise and magnitudes, not scenario structure.",
    "The topology is small (8 services); results show relative robustness on this benchmark, "
    "not superiority over commercial products or production data.",
    "LLM baselines depend on prompt wording and model choice; the exact prompts are published "
    "with each report.",
    "Hybrid accuracy equals the engine's by design; its measured contribution is grounded "
    "explanation.",
    "Simulated telemetry is much cleaner than production telemetry.",
]


def parse_seed_spec(value: str) -> list[int]:
    value = value.strip().lower()
    if value == "heldout":
        return DEFAULT_HELDOUT.copy()
    if value == "tuning":
        return DEFAULT_TUNING.copy()
    if value == "demo":
        return [0]
    result: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = (int(item) for item in part.split("-", 1))
            result.extend(range(start, end + 1))
        else:
            result.append(int(part))
    return sorted(set(result))


class EvalRunner:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.topology = load_topology(self.settings.topology_path)
        self.scenarios = load_scenarios(self.settings.topology_path.parent, self.topology)

    def select_scenarios(self, selection: str) -> list[Any]:
        if selection.strip().lower() == "all":
            return self.scenarios
        wanted = {item.strip() for item in selection.split(",") if item.strip()}
        selected = [scenario for scenario in self.scenarios if scenario.id in wanted]
        missing = wanted - {scenario.id for scenario in selected}
        if missing:
            raise ValueError(f"unknown scenarios: {', '.join(sorted(missing))}")
        return selected

    def _render(self, events: list[Any], scenario: Any, *, include_topology: bool) -> str:
        """The one place baseline input is rendered, so the estimate and the run cannot drift."""
        return render_baseline_input(
            events,
            topology=self.topology,
            include_topology=include_topology,
            # spec: the metric window starts 120 s before the fault time T0
            metric_window_start=EPOCH_MS + (scenario.warmup_s - 120) * 1000,
        )

    def estimate_input_tokens(
        self,
        *,
        scenarios: list[Any],
        seeds: list[int],
        approaches: list[str],
        runs: int = 1,
        hybrid_seeds: set[int] | None = None,
    ) -> int:
        """Estimate prompt tokens without calling a provider.

        This intentionally uses the real renderer and representative incident payloads, so the
        dry-run estimate tracks changes to the baseline input rather than a hand-maintained guess.
        The estimate is approximate because provider tokenizers differ.
        """
        total_chars = 0
        for scenario in scenarios:
            for seed in seeds:
                events = generate(scenario, self.topology, seed)
                if "llm_raw" in approaches:
                    total_chars += (
                        len(
                            build_prompt(
                                self._render(events, scenario, include_topology=False),
                                include_topology=False,
                            )
                        )
                        * runs
                    )
                if "llm_raw_topology" in approaches:
                    total_chars += (
                        len(
                            build_prompt(
                                self._render(events, scenario, include_topology=True),
                                include_topology=True,
                            )
                        )
                        * runs
                    )
                if "hybrid" in approaches and (hybrid_seeds is None or seed in hybrid_seeds):
                    incident = run_batch(events, InMemoryTopology(self.topology)).incident
                    total_chars += len(
                        json.dumps(incident.model_dump(mode="json") if incident else {})
                    )
        return max(1, round(total_chars / 4)) if total_chars else 0

    async def run(
        self,
        *,
        scenarios: list[Any],
        seeds: list[int],
        approaches: list[str],
        runs: int = 1,
        hybrid_seeds: set[int] | None = None,
        baseline_provider: LLMProvider | None = None,
        agent_provider: LLMProvider | None = None,
    ) -> tuple[dict[str, Any], list[RunRecord]]:
        records: list[RunRecord] = []
        prompt_dir: dict[str, str] = {
            "baseline_prompt_version": BASELINE_PROMPT_VERSION,
            "baseline_system.txt": SYSTEM_PROMPT,
        }
        for scenario in scenarios:
            for seed in seeds:
                events = generate(scenario, self.topology, seed)
                engine_result = run_batch(events, InMemoryTopology(self.topology))
                engine_hash = _sha256_json([event.model_dump(mode="json") for event in events])
                if "engine" in approaches:
                    determinism_ok = _engine_determinism(events, self.topology, engine_result)
                    records.append(
                        RunRecord(
                            approach="engine",
                            scenario=scenario.id,
                            seed=seed,
                            run_index=0,
                            input_sha256=engine_hash,
                            raw_output=json.dumps(_engine_output(engine_result), sort_keys=True),
                            parsed_output=_engine_output(engine_result),
                            grade=grade_engine(engine_result, scenario).model_copy(
                                update={"determinism_ok": determinism_ok}
                            ),
                        )
                    )
                if "hybrid" in approaches and (hybrid_seeds is None or seed in hybrid_seeds):
                    records.append(
                        await self._hybrid_record(
                            scenario,
                            seed,
                            engine_result.incident,
                            engine_hash,
                            agent_provider,
                        )
                    )
                rendered_cache: dict[bool, str] = {}
                for approach, include_topology in (("llm_raw", False), ("llm_raw_topology", True)):
                    if approach not in approaches:
                        continue
                    rendered = rendered_cache.setdefault(
                        include_topology,
                        self._render(events, scenario, include_topology=include_topology),
                    )
                    prompt_dir[f"{approach}.txt"] = build_prompt(
                        rendered, include_topology=include_topology
                    )
                    for run_index in range(runs):
                        records.append(
                            await self._baseline_record(
                                approach,
                                scenario,
                                seed,
                                run_index,
                                rendered,
                                include_topology,
                                baseline_provider,
                            )
                        )
        aggregates = [item.model_dump(mode="json") for item in aggregate_records(records)]
        report = {
            "meta": {
                "generated_at": datetime.now(UTC).isoformat(),
                "git_commit": _git_commit(),
                "seed_set": "heldout" if seeds == DEFAULT_HELDOUT else "custom",
                "seeds": seeds,
                "scenarios": [scenario.id for scenario in scenarios],
                "approaches": approaches,
                "runs": runs,
                "baseline_provider": baseline_provider.name if baseline_provider else None,
                "baseline_model": baseline_provider.model if baseline_provider else None,
                "agent_provider": agent_provider.name if agent_provider else None,
                "agent_model": agent_provider.model if agent_provider else None,
                "reasoning_effort": self.settings.llm_reasoning_effort,
                "sampling": "provider defaults; temperature is not sent to reasoning models",
                "max_output_tokens": self.settings.llm_max_output_tokens,
                "prompt_version": BASELINE_PROMPT_VERSION,
                "heldout_eval_count": _heldout_count(ROOT / "eval_results")
                + (1 if seeds == DEFAULT_HELDOUT else 0),
            },
            "engine_config": asdict(EngineConfig()),
            "warnings": _warnings(aggregates),
            "results": aggregates,
            "per_run_index": [
                {
                    "approach": item.approach,
                    "scenario": item.scenario,
                    "seed": item.seed,
                    "run_index": item.run_index,
                }
                for item in records
            ],
            "limitations": LIMITATIONS,
            "prompts": prompt_dir,
        }
        return report, records

    async def _baseline_record(
        self,
        approach: str,
        scenario: Any,
        seed: int,
        run_index: int,
        rendered: str,
        include_topology: bool,
        provider: LLMProvider | None,
    ) -> RunRecord:
        input_hash = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
        if provider is None:
            return RunRecord(
                approach=approach,
                scenario=scenario.id,
                seed=seed,
                run_index=run_index,
                input_sha256=input_hash,
                grade=Grade(
                    top1_correct=False,
                    top3_contains=False,
                    false_blame=False,
                    false_alarm=False,
                ),
                error="LLM provider unavailable; no baseline call was made",
                status="not_run",
            )
        request = LLMRequest(
            model=provider.model,
            messages=[
                Message(role="system", content=SYSTEM_PROMPT),
                Message(
                    role="user", content=build_prompt(rendered, include_topology=include_topology)
                ),
            ],
            temperature=0.0,
            max_tokens=self.settings.llm_max_output_tokens,
        )
        started = time.perf_counter()
        raw_outputs: list[str] = []
        usage: dict[str, int | float] = {}
        error: str | None = None
        parsed: BaselineAnswer | None = None
        status: RunStatus = "ok"
        for attempt in range(2):
            try:
                response = await provider.generate(request)
            except Exception as exc:  # provider or network failure: nothing to repair or score
                error = type(exc).__name__ + ": " + str(exc)
                status = "provider_error"
                break
            usage = response.usage
            raw_outputs.append(response.message.content)
            try:
                parsed = parse_output(response.message.content)
                error = None
                status = "ok"
                break
            except ValueError as exc:  # json.JSONDecodeError is a ValueError
                error = type(exc).__name__ + ": " + str(exc)
                status = "parse_error"
                if attempt == 0:
                    request.messages.append(
                        Message(
                            role="user",
                            content=(
                                "Repair once: return only valid JSON matching the requested schema."
                            ),
                        )
                    )
        latency = round((time.perf_counter() - started) * 1000)
        grade = (
            grade_baseline(parsed, scenario.ground_truth)
            if parsed
            else Grade(
                top1_correct=False,
                top3_contains=False,
                false_blame=False,
                false_alarm=False,
            )
        )
        return RunRecord(
            approach=approach,
            scenario=scenario.id,
            seed=seed,
            run_index=run_index,
            input_sha256=input_hash,
            raw_output="\n--- repair attempt ---\n".join(raw_outputs) if raw_outputs else None,
            parsed_output=parsed.model_dump(mode="json") if parsed else None,
            grade=grade,
            latency_ms=latency,
            usage=usage,
            error=error,
            status=status,
        )

    async def _hybrid_record(
        self,
        scenario: Any,
        seed: int,
        incident: Incident | None,
        input_hash: str,
        provider: LLMProvider | None,
    ) -> RunRecord:
        if incident is None:
            grade = Grade(
                top1_correct=not scenario.ground_truth.expect_incident,
                top3_contains=not scenario.ground_truth.expect_incident,
                false_blame=False,
                false_alarm=False,
                grounding_pass=provider is not None,
                mode="TEMPLATE" if provider is None else "LIVE",
                steps=0,
            )
            return RunRecord(
                approach="hybrid",
                scenario=scenario.id,
                seed=seed,
                run_index=0,
                input_sha256=input_hash,
                parsed_output={"incident_detected": False},
                grade=grade,
            )
        started = time.perf_counter()
        result = await InvestigationAgent().investigate(incident, provider=provider)
        grade = grade_hybrid(result, scenario, incident)
        return RunRecord(
            approach="hybrid",
            scenario=scenario.id,
            seed=seed,
            run_index=0,
            input_sha256=input_hash,
            raw_output=result.model_dump_json(),
            parsed_output=result.model_dump(mode="json"),
            grade=grade,
            latency_ms=round((time.perf_counter() - started) * 1000),
            usage=result.usage.model_dump(mode="json", exclude_none=True),
        )


def write_artifacts(report: dict[str, Any], records: list[RunRecord], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "prompts").mkdir(exist_ok=True)
    prompts = report.pop("prompts", {})
    for name, content in prompts.items():
        if name == "baseline_prompt_version":
            continue
        (output_dir / "prompts" / name).write_text(str(content), encoding="utf-8")
    (output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (output_dir / "runs.jsonl").write_text(
        "".join(item.model_dump_json() + "\n" for item in records), encoding="utf-8"
    )
    (output_dir / "report.md").write_text(_markdown_report(report), encoding="utf-8")
    latest = output_dir.parent / "latest"
    latest.mkdir(parents=True, exist_ok=True)
    for name in ("report.json", "report.md", "runs.jsonl"):
        (latest / name).write_text(
            (output_dir / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    if report.get("meta", {}).get("seed_set") == "heldout":
        log = output_dir.parent / ".heldout_log"
        with log.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {"timestamp": report["meta"]["generated_at"], "seeds": report["meta"]["seeds"]}
                )
                + "\n"
            )


def _warnings(aggregates: list[dict[str, Any]]) -> list[str]:
    """Plain-language notes for every approach that did not fully run; shown above the results."""
    totals: dict[str, dict[str, int]] = {}
    scored: dict[str, int] = {}
    for row in aggregates:
        scored[row["approach"]] = scored.get(row["approach"], 0) + row["n"]
        for reason, count in row.get("unscored", {}).items():
            totals.setdefault(row["approach"], {})[reason] = (
                totals.get(row["approach"], {}).get(reason, 0) + count
            )
    notes: list[str] = []
    for approach, reasons in sorted(totals.items()):
        detail = ", ".join(
            f"{count} {reason.replace('_', ' ')}" for reason, count in reasons.items()
        )
        if scored.get(approach, 0) == 0:
            notes.append(
                f"{approach}: no answers were produced ({detail}). No accuracy is reported."
            )
        else:
            notes.append(f"{approach}: some runs produced no answer and are not scored ({detail}).")
    return notes


def _markdown_report(report: dict[str, Any]) -> str:
    meta = report["meta"]
    lines = [
        "# Kea evaluation report",
        "",
        f"Seed set: `{meta['seed_set']}` (seeds {meta['seeds'][0]} to {meta['seeds'][-1]})",
        f"Baseline model: `{meta.get('baseline_model') or 'not run'}`, "
        f"agent model: `{meta.get('agent_model') or 'template'}`, "
        f"prompt `{meta['prompt_version']}`, commit `{meta['git_commit']}`",
        "",
    ]
    if report.get("warnings"):
        lines += ["## Read this first", "", *[f"- {item}" for item in report["warnings"]], ""]
    lines += [
        "| Approach | Scenario | Top-1 | Top-3 | False blame | False alarm | Not scored |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for row in report["results"]:
        skipped = ", ".join(
            f"{v} {k.replace('_', ' ')}" for k, v in row.get("unscored", {}).items()
        )
        lines.append(
            f"| {row['approach']} | {row['scenario']} | {_cell(row['top1_correct'])} | "
            f"{_cell(row['top3_contains'])} | {_cell(row['false_blame'])} | "
            f"{_cell(row['false_alarm'])} | {skipped or 'none'} |"
        )
    lines.extend(["", "## Limitations", "", *[f"- {item}" for item in report["limitations"]], ""])
    return "\n".join(lines)


def _cell(value: dict[str, Any]) -> str:
    if value["n"] == 0:
        return "not run"
    return f"{value['k']}/{value['n']} ({value['ci_low']:.2f}-{value['ci_high']:.2f})"


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _engine_output(result: Any) -> dict[str, Any]:
    return {
        "updates": [item.model_dump(mode="json") for item in result.updates],
        "anomalies": [item.model_dump(mode="json") for item in result.anomalies],
        "candidates": [item.model_dump(mode="json") for item in result.candidates],
        "rejected_candidates": [
            item.model_dump(mode="json") for item in result.rejected_candidates
        ],
        "incident_open": result.incident_open,
        "incident": result.incident.model_dump(mode="json") if result.incident else None,
    }


def _engine_determinism(events: list[Any], topology: Any, result: Any) -> bool:
    """Check repeated batch output and the incremental state path agree byte-for-byte."""
    expected = _sha256_json(_engine_output(result))
    repeated = run_batch(events, InMemoryTopology(topology))
    repeated_hash = _sha256_json(_engine_output(repeated))
    if not events:
        return expected == repeated_hash
    state = EngineState(events[0].run_id, InMemoryTopology(topology))
    for event in events:
        state.ingest(event)
    incremental_hash = _sha256_json(_engine_output(state.result()))
    return expected == repeated_hash == incremental_hash


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _heldout_count(directory: Path) -> int:
    log = directory / ".heldout_log"
    return len(log.read_text(encoding="utf-8").splitlines()) if log.exists() else 0
