"""`python -m app.eval run` command."""

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path

from app.config import ROOT, get_settings
from app.eval.runner import EvalRunner, parse_seed_spec, write_artifacts
from app.llm.factory import provider_for_settings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.eval")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run the offline benchmark")
    run.add_argument("--scenarios", default="all")
    run.add_argument("--seeds", default="heldout")
    run.add_argument(
        "--approaches",
        default="engine,llm_raw,llm_raw_topology,hybrid",
        help="comma-separated engine,llm_raw,llm_raw_topology,hybrid",
    )
    run.add_argument("--runs", type=int, default=1)
    run.add_argument("--hybrid-seeds", default=None)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--yes", action="store_true")
    run.add_argument("--output", type=Path, default=None)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command != "run":
        raise SystemExit(2)
    settings = get_settings()
    runner = EvalRunner(settings)
    scenarios = runner.select_scenarios(args.scenarios)
    seeds = parse_seed_spec(args.seeds)
    approaches = [item.strip() for item in args.approaches.split(",") if item.strip()]
    hybrid_seed_values = parse_seed_spec(args.hybrid_seeds) if args.hybrid_seeds else None
    if hybrid_seed_values is None and "hybrid" in approaches:
        hybrid_seed_values = seeds[:3]
    llm_calls = (
        len(scenarios)
        * len(seeds)
        * args.runs
        * sum(item in {"llm_raw", "llm_raw_topology"} for item in approaches)
    )
    if "hybrid" in approaches:
        llm_calls += len(scenarios) * len(hybrid_seed_values or [])
    hybrid_seeds = set(hybrid_seed_values) if hybrid_seed_values is not None else None
    estimated_tokens = runner.estimate_input_tokens(
        scenarios=scenarios,
        seeds=seeds,
        approaches=approaches,
        runs=args.runs,
        hybrid_seeds=hybrid_seeds,
    )
    print(
        f"Plan: {len(scenarios)} scenarios x {len(seeds)} seeds x {args.runs} run(s); "
        f"approaches={','.join(approaches)}; planned LLM calls={llm_calls}; "
        f"estimated input tokens={estimated_tokens} (approx.)"
    )
    if args.dry_run:
        print("Dry run: no provider calls were made and no artifacts were written.")
        return
    if llm_calls > 150 and not args.yes:
        raise SystemExit("planned LLM calls exceed 150; rerun with --yes")
    output_root = ROOT / "eval_results"
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output or output_root / timestamp
    report, records = asyncio.run(
        runner.run(
            scenarios=scenarios,
            seeds=seeds,
            approaches=approaches,
            runs=args.runs,
            hybrid_seeds=set(hybrid_seeds) if hybrid_seeds else None,
            baseline_provider=provider_for_settings(settings, "baseline"),
            agent_provider=provider_for_settings(settings, "agent"),
        )
    )
    write_artifacts(report, records, output_dir)
    print(f"Wrote {output_dir / 'report.json'} ({len(records)} runs)")


if __name__ == "__main__":
    main()
