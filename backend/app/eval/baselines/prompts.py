"""Versioned prompts for the LLM-only baselines and constrained reranker."""

from typing import Any

BASELINE_PROMPT_VERSION = "baseline-v1"
RERANK_PROMPT_VERSION = "hybrid-rerank-v1"

SYSTEM_PROMPT = """You are an experienced site reliability engineer investigating telemetry.
Use only the supplied telemetry. Consider timing, dependency direction when provided, and the
possibility that a recent deployment is unrelated. It is valid to conclude that there is no
incident. Return JSON only, matching this schema:
{"incident_detected": true, "ranked_hypotheses": [{"kind": "deployment" or
"service_fault", "service": "name", "deployment_id": "id or null"}],
"explanation": "short text"}
Return at most three hypotheses. Do not include markdown fences or additional keys."""


def build_prompt(rendered: str, *, include_topology: bool) -> str:
    label = "telemetry with the service topology" if include_topology else "raw telemetry"
    return f"Investigate this {label}:\n\n{rendered}"


RERANK_SYSTEM_PROMPT = """You are reviewing a deterministic root-cause engine's top candidates.
Reorder only the candidate IDs provided by the user. Do not add, remove, rename, or invent a
candidate. Use only the supplied evidence statements. Return JSON only:
{"ordered_candidate_ids":["candidate-id"],"evidence_ids":["E-0001"],"explanation":"short reason"}
The ordered list must contain each supplied candidate exactly once. Evidence IDs must come from
the supplied candidates. Do not use probabilities or confidence language."""


def build_rerank_prompt(candidates: list[dict[str, Any]]) -> str:
    lines = ["Reorder these candidates, preserving the candidate IDs exactly:"]
    for candidate in candidates:
        lines.append(
            f"\nCANDIDATE {candidate['candidate_id']}\n"
            f"kind={candidate['kind']} service={candidate['service']} "
            f"deployment_id={candidate['deployment_id']} original_rank={candidate['rank']} "
            f"score={candidate['score']}"
        )
        for evidence in candidate["evidence"]:
            lines.append(f"  {evidence['evidence_id']}: {evidence['statement']}")
    return "\n".join(lines)
