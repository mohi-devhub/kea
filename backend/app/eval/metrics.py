"""Small-sample benchmark statistics."""

from collections import Counter
from collections.abc import Iterable
from math import sqrt

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
