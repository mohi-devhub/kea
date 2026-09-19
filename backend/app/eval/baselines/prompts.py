"""Versioned prompts for the two P1 LLM-only baselines."""

BASELINE_PROMPT_VERSION = "baseline-v1"

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
