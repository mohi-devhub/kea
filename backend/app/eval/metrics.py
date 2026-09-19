"""Small-sample benchmark statistics."""

from collections import Counter
from collections.abc import Iterable
from math import sqrt
from statistics import median

from app.eval.models import UNSCORED, AggregateResult, RunRecord, WilsonInterval


def wilson_interval(k: int, n: int, z: float = 1.96) -> WilsonInterval:
    if n <= 0:
        return WilsonInterval(k=0, n=0, ci_low=0.0, ci_high=0.0)
    p = k / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    spread = z * sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denominator
    return WilsonInterval(
        k=k, n=n, ci_low=max(0.0, centre - spread), ci_high=min(1.0, centre + spread)
    )


def _signature(record: RunRecord) -> tuple[object, ...] | None:
    """What an answer commits to: whether it saw an incident and its top hypothesis."""
    out = record.parsed_output
    if not out or "incident_detected" not in out:
        return None
    hyps = out.get("ranked_hypotheses") or []
    top = hyps[0] if hyps else {}
    return (
        bool(out["incident_detected"]),
        top.get("kind"),
        top.get("service"),
        top.get("deployment_id"),
    )


def consistency(records: list[RunRecord]) -> dict[str, object] | None:
    """Run-to-run agreement: for each seed with several runs of the same input, the share of runs
    that match the most common answer. 1.0 means the approach always answered the same way."""
    by_seed: dict[int, list[tuple[object, ...]]] = {}
    for record in records:
        signature = _signature(record)
        if signature is not None:
            by_seed.setdefault(record.seed, []).append(signature)
    shares = [max(Counter(sigs).values()) / len(sigs) for sigs in by_seed.values() if len(sigs) > 1]
    if not shares:
        return None
    return {
        "cases": len(shares),
        "runs_per_case": round(sum(len(v) for v in by_seed.values() if len(v) > 1) / len(shares)),
        "agreement": sum(shares) / len(shares),
        "unanimous_cases": sum(1 for share in shares if share == 1.0),
    }


def cost_summary(records: Iterable[RunRecord]) -> dict[str, dict[str, float | int | None]]:
    """Per approach: how many analyses, how long each took, and how many tokens they used."""
    grouped: dict[str, list[RunRecord]] = {}
    for record in records:
        if record.status not in UNSCORED:
            grouped.setdefault(record.approach, []).append(record)
    out: dict[str, dict[str, float | int | None]] = {}
    for approach, group in sorted(grouped.items()):
        latencies = [r.latency_ms for r in group if r.latency_ms is not None]
        tokens = [r.usage.get("total_tokens", 0) for r in group]
        out[approach] = {
            "analyses": len(group),
            "median_latency_ms": round(median(latencies), 2) if latencies else None,
            "median_tokens": int(median(tokens)) if tokens else 0,
            "total_tokens": int(sum(tokens)),
        }
    return out


def aggregate_records(records: Iterable[RunRecord]) -> list[AggregateResult]:
    """Aggregate per (approach, scenario). Runs that produced no answer are counted separately and
    never enter the denominator, so a baseline that did not run shows "not run", not 0 percent."""
    groups: dict[tuple[str, str], list[RunRecord]] = {}
    for record in records:
        groups.setdefault((record.approach, record.scenario), []).append(record)
    output: list[AggregateResult] = []
    for (approach, scenario), group in sorted(groups.items()):
        unscored = Counter(r.status for r in group if r.status in UNSCORED)
        scored = [r for r in group if r.status not in UNSCORED]
        grades = [r.grade for r in scored]
        n = len(grades)
        extra: dict[str, object] = {}
        grounding = [grade.grounding_pass for grade in grades if grade.grounding_pass is not None]
        coverage = [
            grade.evidence_coverage for grade in grades if grade.evidence_coverage is not None
        ]
        if grounding:
            extra["grounding_pass_rate"] = sum(grounding) / len(grounding)
        if coverage:
            extra["evidence_coverage"] = sum(coverage) / len(coverage)
        modes = [grade.mode for grade in grades if grade.mode]
        if modes:
            extra["mode_counts"] = {mode: modes.count(mode) for mode in sorted(set(modes))}
        agreement = consistency(scored)
        if agreement:
            extra["consistency"] = agreement
        determinism = [grade.determinism_ok for grade in grades if grade.determinism_ok is not None]
        if determinism:
            extra["determinism_rate"] = sum(determinism) / len(determinism)
        output.append(
            AggregateResult(
                approach=approach,
                scenario=scenario,
                n=n,
                top1_correct=wilson_interval(sum(grade.top1_correct for grade in grades), n),
                top3_contains=wilson_interval(sum(grade.top3_contains for grade in grades), n),
                false_blame=wilson_interval(sum(grade.false_blame for grade in grades), n),
                false_alarm=wilson_interval(sum(grade.false_alarm for grade in grades), n),
                unscored=dict(unscored),
                parse_errors=sum(1 for r in scored if r.status == "parse_error"),
                extra=extra,
            )
        )
    return output
