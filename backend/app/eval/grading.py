"""Ground-truth grading kept outside the baseline renderer."""

from typing import Any

from app.agent.models import InvestigationResult
from app.eval.models import BaselineAnswer, Grade
from app.models.engine import Incident
from app.simulator.models import GroundTruth, Scenario


def _matches(hypothesis: Any, truth: Any) -> bool:
    if hypothesis is None or truth is None:
        return False
    return bool(
        hypothesis.kind == truth.kind
        and hypothesis.service == truth.service
        and (hypothesis.kind != "deployment" or hypothesis.deployment_id == truth.deployment_id)
    )


def _false_blame(hypothesis: Any, truth: GroundTruth) -> bool:
    if hypothesis is None:
        return False
    if hypothesis.service in truth.must_not_implicate:
        return True
    return any(
        hypothesis.kind == "deployment"
        and hypothesis.deployment_id == rejection.candidate_id.removeprefix("deployment:")
        for rejection in truth.must_reject
    )


def _base_grade(
    *,
    detected: bool,
    hypotheses: list[Any],
    truth: GroundTruth,
) -> Grade:
    top = hypotheses[0] if hypotheses else None
    expected_incident = truth.expect_incident
    top1 = (not expected_incident and not detected) or (
        expected_incident
        and detected
        and truth.root_cause is not None
        and _matches(top, truth.root_cause)
    )
    top3 = (
        top1
        if not expected_incident
        else any(
            truth.root_cause is not None and _matches(item, truth.root_cause)
            for item in hypotheses[:3]
        )
    )
    return Grade(
        top1_correct=top1,
        top3_contains=top3,
        false_blame=expected_incident and _false_blame(top, truth),
        false_alarm=not expected_incident and detected,
    )


def grade_baseline(answer: BaselineAnswer, truth: GroundTruth) -> Grade:
    return _base_grade(
        detected=answer.incident_detected,
        hypotheses=answer.ranked_hypotheses,
        truth=truth,
    )


def grade_engine(result: Any, scenario: Scenario) -> Grade:
    truth = scenario.ground_truth
    incident: Incident | None = result.incident
    candidates = result.candidates
    grade = _base_grade(
        detected=incident is not None,
        hypotheses=[
            type(
                "EngineHypothesis",
                (),
                {
                    "kind": candidate.kind,
                    "service": candidate.service,
                    "deployment_id": candidate.deployment_id,
                },
            )()
            for candidate in candidates
        ],
        truth=truth,
    )
    rejection_map = {item.candidate_id: item.reason_code for item in result.rejected_candidates}
    decoys_ok = all(
        rejection_map.get(item.candidate_id) == item.reason_code for item in truth.must_reject
    )
    if incident is None or not incident.anomalies:
        return grade.model_copy(update={"decoys_rejected_correctly": decoys_ok})
    first_anomaly = min(item.onset_ts for item in incident.anomalies)
    detection_latency = max(0.0, (incident.opened_ts - first_anomaly) / 1000)
    return grade.model_copy(
        update={
            "decoys_rejected_correctly": decoys_ok,
            "detection_latency_s": detection_latency,
            "time_to_correct_s": detection_latency if grade.top1_correct else None,
            "details": {
                "candidate_ids": [item.candidate_id for item in candidates],
                "rejected": rejection_map,
            },
        }
    )


def grade_hybrid(
    result: InvestigationResult, scenario: Scenario, incident: Incident | None
) -> Grade:
    truth = scenario.ground_truth
    top = incident.candidates[0] if incident and incident.candidates else None
    cited = {evidence_id for step in result.narrative_steps for evidence_id in step.evidence_ids}
    top_evidence = set(top.evidence_ids) if top else set()
    addressed = []
    narrative = " ".join(step.text for step in result.narrative_steps).lower()
    for rejection in truth.must_reject:
        addressed.append(
            rejection.candidate_id.lower() in narrative
            or rejection.candidate_id.removeprefix("deployment:").lower() in narrative
        )
    return Grade(
        top1_correct=truth.expect_incident is False
        or result.root_cause_candidate_id == (top.candidate_id if top else None),
        top3_contains=truth.expect_incident is False
        or result.root_cause_candidate_id
        in {candidate.candidate_id for candidate in (incident.candidates[:3] if incident else [])},
        false_blame=False,
        false_alarm=not truth.expect_incident and incident is not None,
        grounding_pass=result.mode != "TEMPLATE",
        evidence_coverage=(len(cited & top_evidence) / len(top_evidence)) if top_evidence else 1.0,
        decoy_addressed=all(addressed) if addressed else True,
        disagreement=result.disagreement is not None,
        steps=len(result.trace),
        mode=result.mode,
    )


def grade_rerank(
    ordered_candidate_ids: list[str],
    original_candidate_ids: list[str],
    incident: Incident | None,
    scenario: Scenario,
    *,
    mode: str,
    grounding_pass: bool | None,
    fallback: bool,
) -> Grade:
    candidates = incident.candidates if incident else []
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    ordered = [
        by_id[candidate_id] for candidate_id in ordered_candidate_ids if candidate_id in by_id
    ]
    grade = _base_grade(
        detected=incident is not None,
        hypotheses=ordered,
        truth=scenario.ground_truth,
    )
    rejected = {
        item.candidate_id: item.reason_code
        for item in (incident.rejected_candidates if incident else [])
    }
    expected_rejected = scenario.ground_truth.must_reject
    decoys_ok = all(
        rejected.get(item.candidate_id) == item.reason_code for item in expected_rejected
    )
    return grade.model_copy(
        update={
            "decoys_rejected_correctly": decoys_ok,
            "grounding_pass": grounding_pass,
            "mode": mode,
            "details": {
                "original_candidate_ids": original_candidate_ids,
                "reranked_candidate_ids": ordered_candidate_ids,
                "fallback": fallback,
            },
        }
    )
