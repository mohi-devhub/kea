"""Checks that model-authored investigations stay inside engine evidence."""

import re

from app.agent.models import InvestigationResult
from app.models.engine import Incident

_NUMBER = re.compile(r"\b(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>x|%|ms|s)\b", re.IGNORECASE)


def validate_grounding(result: InvestigationResult, incident: Incident) -> list[str]:
    failures: list[str] = []
    known_ids = {item.evidence_id for item in incident.evidence}
    result_ids = {item.evidence_id for item in result.evidence}
    if result_ids != known_ids:
        failures.append("result evidence does not match the incident evidence set")
    candidate_ids = {item.candidate_id for item in incident.candidates}
    if (
        result.root_cause_candidate_id not in candidate_ids
        and result.root_cause_candidate_id is not None
    ):
        failures.append("root cause candidate is not an engine candidate")
    if incident.candidates and result.disagreement is None:
        if result.root_cause_candidate_id != incident.candidates[0].candidate_id:
            failures.append("root cause differs from the engine ranking without disagreement")
    for step in result.narrative_steps:
        unknown = set(step.evidence_ids) - known_ids
        if unknown:
            failures.append(f"narrative cites unknown evidence: {sorted(unknown)}")
    evidence_text = " ".join(item.statement for item in incident.evidence)
    evidence_text += " " + " ".join(str(item.data) for item in incident.evidence)
    evidence_numbers = [
        (float(match.group("value")), match.group("unit").lower())
        for match in _NUMBER.finditer(evidence_text)
    ]
    for step in result.narrative_steps:
        for match in _NUMBER.finditer(step.text):
            claim = match.group(0)
            value = float(match.group("value"))
            unit = match.group("unit").lower()
            if not any(
                evidence_unit == unit and abs(value - evidence_value) <= 0.051
                for evidence_value, evidence_unit in evidence_numbers
            ):
                failures.append(f"numeric claim is not present in evidence: {claim}")
    return failures
