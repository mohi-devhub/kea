"""Deterministic, evidence-cited investigation output.

This is intentionally useful without a model key.  It also forms the safe
fallback whenever a provider response fails grounding or is unavailable.
"""

from collections.abc import Iterable

from app.agent.models import InvestigationResult, NarrativeStep, TraceEntry
from app.models.engine import Candidate, Incident


def _evidence_for_step(candidate: Candidate, ref: str, evidence_refs: dict[str, str]) -> list[str]:
    direct = evidence_refs.get(ref)
    if direct:
        return [direct]
    return candidate.evidence_ids[:1]


def build_template_investigation(
    incident: Incident,
    investigation_id: str,
    *,
    trace: Iterable[TraceEntry] = (),
    caveats: list[str] | None = None,
) -> InvestigationResult:
    top = incident.candidates[0] if incident.candidates else None
    evidence_refs = {item.ref: item.evidence_id for item in incident.evidence}
    if top is None:
        summary = "The engine did not identify a causal candidate for this incident."
        steps = [
            NarrativeStep(
                text=(
                    "No ranked candidate is available, so this incident needs manual investigation."
                ),
                evidence_ids=[],
            )
        ]
        root_id = None
    else:
        subject = f"{top.deployment_id} on {top.service}" if top.deployment_id else top.service
        summary = (
            f"The strongest engine candidate is {subject}; the chain below is evidence-backed."
        )
        steps = [
            NarrativeStep(
                text=step.statement,
                evidence_ids=_evidence_for_step(top, step.ref, evidence_refs),
            )
            for step in top.chain
        ]
        if len(steps) < 5:
            # Keep the narrative readable while making the required context explicit.
            steps.extend(
                [
                    NarrativeStep(
                        text=incident.what_changed.statement,
                        evidence_ids=top.evidence_ids,
                    ),
                    NarrativeStep(
                        text=(
                            "The affected service set includes "
                            f"{len(incident.blast_radius.services)} "
                            "services; customer-facing impact is listed in the blast radius."
                        ),
                        evidence_ids=[],
                    ),
                ][: 5 - len(steps)]
            )
        root_id = top.candidate_id
    all_caveats = list(caveats or [])
    if incident.ambiguous:
        all_caveats.append(
            "The engine marked this incident ambiguous; the ranking remains authoritative."
        )
    if not incident.candidates:
        all_caveats.append("No root-cause candidate was available from the deterministic engine.")
    return InvestigationResult(
        investigation_id=investigation_id,
        incident_id=incident.incident_id,
        mode="TEMPLATE",
        provider="template",
        model="deterministic-v1",
        summary=summary,
        root_cause_candidate_id=root_id,
        narrative_steps=steps[:8],
        evidence=incident.evidence,
        blast_radius=incident.blast_radius,
        what_changed=incident.what_changed,
        rejected_candidates=incident.rejected_candidates,
        caveats=all_caveats,
        trace=list(trace),
    )
