"""Live check of the fix flow on the S1 incident against the real demo repo copy.

Run: `uv run python -m scripts.fix_smoke [codex_cli|llm_tool_loop]`. It only ever writes inside
`.sandboxes/`; it prints the proposal summary, never keys or full prompts.
"""

import asyncio
import sys

from app.config import get_settings
from app.engine import InMemoryTopology, run_batch
from app.fix.service import FixService
from app.graph.client import load_topology
from app.llm.factory import provider_for_settings
from app.simulator.generator import generate
from app.simulator.loader import load_scenarios


async def main(backend: str) -> int:
    settings = get_settings()
    topology = load_topology(settings.topology_path)
    scenario = next(
        s for s in load_scenarios(settings.topology_path.parent, topology) if s.id.startswith("s1")
    )
    events = generate(scenario, topology, 0)
    incident = run_batch(events, InMemoryTopology(topology)).incident
    assert incident is not None
    deployments = [e.model_dump(mode="json") for e in events if e.kind == "deployment"]
    service = FixService(
        demo_repo=settings.demo_repo_path,
        sandboxes=settings.sandbox_dir,
        provider=provider_for_settings(settings, "fix"),
        backend_pref=backend,
    )
    created = await service.start(incident, incident.run_id, deployments)
    await service.wait(created.proposal_id)
    proposal = service.get(created.proposal_id)
    print(f"state={proposal.state} backend={proposal.backend} mode={proposal.mode}")
    print(f"error={proposal.error}")
    if proposal.verification.before and proposal.verification.after:
        print(f"before: {proposal.verification.before.summary}")
        print(f"after:  {proposal.verification.after.summary}")
    print(f"approvable={proposal.approvable} reason={proposal.approve_blocked_reason}")
    print(f"files={[f.path for f in proposal.files_changed]} steps={len(proposal.agent_trace)}")
    print(proposal.diff)
    if proposal.explanation:
        print("summary:", proposal.explanation.summary)
    return 0 if proposal.state == "proposed" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "llm_tool_loop")))
