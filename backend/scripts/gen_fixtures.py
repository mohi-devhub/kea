"""Generate WebSocket replay fixtures (CONTRACTS.md section 4) from batch-mode engine output.

Each fixture is a full arc: healthy, fault, incident, prediction made, recovery, resolution and
verification. Payloads match what the live API broadcasts, so the UI has a single code path.
"""

import json
from typing import Any

from app.config import ROOT, get_settings
from app.engine import EngineState, InMemoryTopology
from app.engine.prediction import make_prediction, verify_prediction
from app.graph.client import load_topology
from app.models.engine import Prediction
from app.models.events import DeploymentEvent, LogEvent, MetricEvent, RollbackEvent
from app.models.topology import Topology
from app.simulator.generator import EPOCH_MS, generate
from app.simulator.loader import load_scenarios
from app.simulator.models import Scenario

FIXTURE_SCENARIOS = {"s1_bad_deploy_payment", "s2_postgres_degradation", "s3_red_herring_deploy"}
SEED = 42
SPEED = 10  # ponytail: fixed demo speed; the fixture player controls real pacing
RECOVER_LEAD_S = 15  # recover this long after the last incident anomaly appears
WS_TYPES = {
    "anomaly_opened": "anomaly.opened",
    "anomaly_resolved": "anomaly.resolved",
    "incident_opened": "incident.opened",
    "incident_updated": "incident.updated",
    "incident_resolved": "incident.resolved",
}


def _recover_at_s(scenario: Scenario, topology: Topology, seed: int) -> int:
    """Pick a recovery time after the fault has fully propagated (first pass, no recovery)."""
    events = generate(scenario, topology, seed)
    state = EngineState(events[0].run_id, InMemoryTopology(topology))
    for event in events:
        state.ingest(event)
    last_onset = max(a.onset_ts for a in state.anomalies)
    return -(-(last_onset - EPOCH_MS) // 1000) - scenario.warmup_s + RECOVER_LEAD_S


def build_messages(scenario: Scenario, topology: Topology, seed: int) -> list[dict[str, Any]]:
    """Replay events through the engine and emit full-payload WS envelopes.

    `pending_watch` is engine-internal (no WS type), so the UI derives "watching" from
    `anomaly.opened` while no incident is open.
    """
    recover_s = _recover_at_s(scenario, topology, seed)
    recover_ts = EPOCH_MS + (scenario.warmup_s + recover_s) * 1000
    events = generate(scenario, topology, seed, recover_at_s=recover_s)
    state = EngineState(events[0].run_id, InMemoryTopology(topology))
    messages: list[dict[str, Any]] = []
    prediction: Prediction | None = None

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
        if event.ts >= recover_ts and prediction is None and state.incident is not None:
            prediction = make_prediction(state.incident, event.ts)
            emit("prediction.made", event.ts, prediction.model_dump(mode="json"))
        if isinstance(event, MetricEvent):
            batch.append(
                {"service": event.service, "metric": event.payload.metric, "ts": event.ts,
                 "value": event.payload.value}
            )  # fmt: skip
        elif isinstance(event, DeploymentEvent | RollbackEvent):
            emit("deployment.observed", event.ts, event.model_dump(mode="json"))
        elif isinstance(event, LogEvent):
            emit("log.batch", event.ts, [event.model_dump(mode="json")])
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
                if update.type == "incident_resolved" and prediction is not None:
                    verdict = verify_prediction(
                        prediction, dict(state.service_health), update.sim_ts
                    )
                    emit("prediction.verified", update.sim_ts, verdict.model_dump(mode="json"))
    if batch:
        emit("metrics.batch", batch[0]["ts"], batch)
    emit("run.stopped", messages[-1]["sim_ts"], {"status": "completed"})
    return messages


def main() -> None:
    settings = get_settings()
    topology = load_topology(settings.topology_path)
    output_dir = ROOT / "frontend" / "public" / "fixtures"
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
