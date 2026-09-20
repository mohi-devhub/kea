"""Short, grounded explanation shown next to the diff (docs/FIX_FLOW_SPEC.md section 9)."""

import re

from app.fix.models import FileChange, FixExplanation

_SENTENCE = re.compile(r"[.!?](?:\s|$)")
_FORBIDDEN = re.compile(r"\b(probabilit|confiden|percent|\d+\s?%)", re.I)


def _sentences(text: str) -> int:
    return len(_SENTENCE.findall(text.strip())) or (1 if text.strip() else 0)


def validate_explanation(
    explanation: FixExplanation, files: list[FileChange], evidence_ids: set[str]
) -> list[str]:
    """Deterministic grounding checks; an empty list means the explanation may be shown."""
    problems = []
    for name, text in (
        ("summary", explanation.summary),
        ("why_it_fixes", explanation.why_it_fixes),
    ):
        if not text.strip():
            problems.append(f"{name} is empty")
        if _sentences(text) > 3:
            problems.append(f"{name} is longer than 3 sentences")
        if _FORBIDDEN.search(text):
            problems.append(f"{name} uses probability or confidence language")
    for evidence_id in explanation.evidence_ids:
        if evidence_id not in evidence_ids:
            problems.append(f"unknown evidence id {evidence_id}")
    paths = {f.path for f in files}
    for mentioned in re.findall(
        r"[\w./-]+\.py", explanation.summary + " " + explanation.why_it_fixes
    ):
        if mentioned not in paths and not any(p.endswith(mentioned) for p in paths):
            problems.append(f"mentions {mentioned}, which the diff does not change")
    return problems


def template_explanation(
    files: list[FileChange], candidate_id: str, evidence: list[dict[str, str]]
) -> FixExplanation:
    """Deterministic fallback built from diff stats and the incident evidence."""
    names = ", ".join(f.path for f in files) or "no files"
    adds = sum(f.additions for f in files)
    dels = sum(f.deletions for f in files)
    return FixExplanation(
        summary=f"Changes {names} (+{adds} -{dels}) to address {candidate_id}.",
        why_it_fixes=(
            "The engine ranked this deployment as the root cause, and the change targets the "
            "code it introduced. Review the diff and the test results before approving."
        ),
        evidence_ids=[e["evidence_id"] for e in evidence[:3]],
        risks=["Template explanation: the model did not supply one."],
    )
