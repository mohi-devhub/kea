"""Generate WebSocket replay fixtures (CONTRACTS.md section 4) from batch-mode engine output."""

import json
from typing import Any

from app.config import ROOT, get_settings
from app.engine import EngineState, InMemoryTopology
from app.graph.client import load_topology
from app.models.events import DeploymentEvent, MetricEvent
from app.models.topology import Topology
from app.simulator.generator import generate
from app.simulator.loader import load_scenarios
from app.simulator.models import Scenario

FIXTURE_SCENARIOS = {"s1_bad_deploy_payment", "s2_postgres_degradation", "s3_red_herring_deploy"}
SEED = 42
SPEED = 10  # ponytail: fixed demo speed; the fixture player controls real pacing
WS_TYPES = {
    "anomaly_opened": "anomaly.opened",
    "anomaly_resolved": "anomaly.resolved",
    "incident_opened": "incident.opened",
    "incident_updated": "incident.updated",
    "incident_resolved": "incident.resolved",
}


def build_messages(scenario: Scenario, topology: Topology, seed: int) -> list[dict[str, Any]]:
    """Replay events through the engine and emit full-payload WS envelopes.

    `pending_watch` is engine-internal (no WS type), so the UI derives "watching" from
    `anomaly.opened` while no incident is open.
    """
    events = generate(scenario, topology, seed)
    state = EngineState(events[0].run_id, InMemoryTopology(topology))
    messages: list[dict[str, Any]] = []

    def emit(kind: str, ts: int, payload: Any) -> None:
        messages.append(
            {
                "type": kind, "run_id": state.run_id, "seq": len(messages), "sim_ts": ts,
                "payload": payload,
            }
        )  # fmt: skip

    emit("run.started", events[0].ts, {"scenario": scenario.id, "seed": seed, "speed": SPEED})
    batch: list[dict[str, Any]] = []
    for event in events:
        if batch and batch[0]["ts"] != event.ts:
            emit("metrics.batch", batch[0]["ts"], batch)
            emit("sim.clock", batch[0]["ts"], {"sim_ts": batch[0]["ts"], "speed": SPEED})
            batch = []
        if isinstance(event, MetricEvent):
            batch.append(
                {"service": event.service, "metric": event.payload.metric, "ts": event.ts,
                 "value": event.payload.value}
            )  # fmt: skip
        elif isinstance(event, DeploymentEvent):
            emit(
                "deployment.observed",
                event.ts,
                {"service": event.service, **event.payload.model_dump()},
            )
        for update in state.ingest(event):
            if update.type == "service_health_changed":
                emit("service.health", update.sim_ts, update.payload)
            elif update.type.startswith("anomaly_"):
                anomaly = next(
                    a for a in state.anomalies if a.anomaly_id == update.payload["anomaly_id"]
                )
                emit(WS_TYPES[update.type], update.sim_ts, anomaly.model_dump(mode="json"))
            elif update.type in WS_TYPES and state.incident:
                emit(WS_TYPES[update.type], update.sim_ts, state.incident.model_dump(mode="json"))
    if batch:
        emit("metrics.batch", batch[0]["ts"], batch)
    return messages


def main() -> None:
    settings = get_settings()
    topology = load_topology(settings.topology_path)
    output_dir = ROOT / "frontend" / "fixtures"
    output_dir.mkdir(parents=True, exist_ok=True)
    for scenario in load_scenarios(settings.topology_path.parent, topology):
        if scenario.id not in FIXTURE_SCENARIOS:
            continue
        path = output_dir / f"{scenario.id}-{SEED}.jsonl"
        path.write_text(
            "".join(
                json.dumps(m, sort_keys=True) + "\n"
                for m in build_messages(scenario, topology, SEED)
            )
        )
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
