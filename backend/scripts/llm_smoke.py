"""Live check of the configured provider.

Sends only simulated incident data (guarded by SafeProvider); prints statistics, never keys or
full prompts. Run: `uv run python -m scripts.llm_smoke`.
"""

# ruff: noqa: E501

import asyncio
import os
import sys
import time

from app.agent.runner import InvestigationAgent
from app.agent.tools import ToolContext
from app.api.store import RunView
from app.config import get_settings
from app.engine import InMemoryTopology, run_batch
from app.graph.client import load_topology
from app.llm.factory import provider_for_settings
from app.llm.models import LLMRequest, Message
from app.llm.safety import find_secret
from app.simulator.generator import generate
from app.simulator.loader import load_scenarios


async def main() -> int:
    settings = get_settings()
    # record keeps a local copy for offline replay (git-ignored); LLM_CACHE_MODE=replay sends nothing
    settings.llm_cache_mode = os.environ.get("LLM_CACHE_MODE") or "record"
    provider = provider_for_settings(settings)
    if provider is None:
        print("template mode: set LLM_PROVIDER, LLM_MODEL and the key in .env")
        return 1
    print(f"provider={provider.name} model={provider.model} cache={settings.llm_cache_mode}")

    started = time.perf_counter()
    try:
        ping = await provider.generate(
            LLMRequest(
                model=provider.model,
                messages=[Message(role="user", content="Reply with the single word: ok")],
            )
        )
    except Exception as exc:
        print(f"connectivity FAILED: {exc}")
        return 1
    print(
        f"connectivity ok in {time.perf_counter() - started:.1f}s, reply={ping.message.content.strip()[:20]!r}, tokens={ping.usage.get('total_tokens')}"
    )

    topology = load_topology(settings.topology_path)
    scenario = next(
        s
        for s in load_scenarios(settings.topology_path.parent, topology)
        if s.id == "s2_postgres_degradation"
    )
    result = run_batch(generate(scenario, topology, 0), InMemoryTopology(topology))
    incident = result.incident
    assert incident is not None
    outbound = incident.model_dump_json()
    print(
        f"outbound incident payload: {len(outbound)} chars, secret scan: {find_secret(outbound, settings.secret_values()) or 'clean'}"
    )

    view = RunView(run_id=incident.run_id)
    steps: list[str] = []

    async def on_step(entry) -> None:  # type: ignore[no-untyped-def]
        steps.append(f"{entry.kind}:{entry.name}")

    started = time.perf_counter()
    investigation = await InvestigationAgent(settings.agent_max_steps).investigate(
        incident, provider=provider, tool_context=ToolContext(view, topology), on_step=on_step
    )
    top = incident.candidates[0].candidate_id
    print(
        f"investigation in {time.perf_counter() - started:.1f}s: mode={investigation.mode} provider={investigation.provider} model={investigation.model}"
    )
    print(f"root cause matches engine ({top}): {investigation.root_cause_candidate_id == top}")
    print(
        f"narrative steps: {len(investigation.narrative_steps)}, evidence-cited: {sum(1 for s in investigation.narrative_steps if s.evidence_ids)}"
    )
    print(f"tokens: {investigation.usage.model_dump()}")
    print(f"caveats: {investigation.caveats or 'none'}")
    print(f"trace: {steps}")
    print("summary:", investigation.summary[:200])
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
