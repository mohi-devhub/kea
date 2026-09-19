"""In-memory live materialized view and WebSocket fan-out."""

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from app.models.engine import Incident, Prediction, PredictionVerification
from app.models.events import Event


@dataclass
class RunView:
    run_id: str
    scenario: str | None = None
    seed: int | None = None
    speed: float | None = None
    status: str = "running"
    sim_ts: int = 0
    events: deque[Event] = field(default_factory=lambda: deque(maxlen=5000))
    incident: Incident | None = None
    prediction: Prediction | None = None
    verification: PredictionVerification | None = None
    health: dict[str, str] = field(default_factory=dict)
    metrics: dict[tuple[str, str], deque[dict[str, Any]]] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=500))
    )
    logs: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=500))
    deployments: list[dict[str, Any]] = field(default_factory=list)
    updates: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=2000))
    pending_metrics: list[dict[str, Any]] = field(default_factory=list)


class RunStore:
    def __init__(self) -> None:
        self.runs: dict[str, RunView] = {}
        self.clients: set[asyncio.Queue[dict[str, Any]]] = set()
        self._seq = 0
        self.retired_runs: set[str] = set()

    def create(self, run_id: str, scenario: str, seed: int, speed: float) -> RunView:
        run = RunView(run_id=run_id, scenario=scenario, seed=seed, speed=speed)
        self.runs[run_id] = run
        return run

    def record_event(self, event: Event) -> None:
        run = self.runs.setdefault(event.run_id, RunView(event.run_id))
        run.events.append(event)
        run.sim_ts = max(run.sim_ts, event.ts)
        if event.kind == "metric":
            point = {
                "service": event.service,
                "metric": event.payload.metric,
                "ts": event.ts,
                "value": event.payload.value,
            }
            run.metrics[(event.service, event.payload.metric)].append(point)
            run.pending_metrics.append(point)
        elif event.kind == "log":
            run.logs.append(event.model_dump(mode="json"))
        elif event.kind == "deployment":
            run.deployments.append(event.model_dump(mode="json"))

    async def update(self, update: dict[str, Any]) -> None:
        if str(update.get("run_id")) in self.retired_runs:
            return
        run = self.runs.setdefault(update["run_id"], RunView(update["run_id"]))
        run.sim_ts = max(run.sim_ts, int(update.get("sim_ts", 0)))
        typ = update.get("type")
        payload = update.get("payload", {})
        run.updates.append(update)
        if (
            typ in {"incident_opened", "incident_updated", "incident_resolved"}
            and "incident" in payload
        ):
            run.incident = Incident.model_validate(payload["incident"])
            if typ == "incident_resolved":
                run.status = "resolved"
        elif typ == "prediction.made":
            run.prediction = Prediction.model_validate(payload)
        elif typ == "prediction.verified":
            run.verification = PredictionVerification.model_validate(payload)
        if typ == "service_health_changed":
            run.health[str(payload["service"])] = str(payload["health"])
        ws_type = {
            "anomaly_opened": "anomaly.opened",
            "anomaly_resolved": "anomaly.resolved",
            "service_health_changed": "service.health",
            "incident_opened": "incident.opened",
            "incident_updated": "incident.updated",
            "incident_resolved": "incident.resolved",
        }.get(str(typ), typ)
        if ws_type == "pending_watch":
            return
        ws_payload = payload
        if str(typ).startswith("incident") and "incident" in payload:
            ws_payload = payload["incident"]
        await self.broadcast({**update, "type": ws_type, "payload": ws_payload})

    async def flush_metrics(self, force: bool = False) -> None:
        for run in self.runs.values():
            if not run.pending_metrics:
                continue
            if not force and len(run.pending_metrics) < 25:
                continue
            batch = run.pending_metrics
            run.pending_metrics = []
            await self.broadcast(
                {
                    "type": "metrics.batch",
                    "run_id": run.run_id,
                    "seq": self._seq,
                    "sim_ts": run.sim_ts,
                    "payload": batch,
                }
            )
            self._seq += 1

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)
        self.clients.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self.clients.discard(queue)

    async def broadcast(self, message: dict[str, Any]) -> None:
        for queue in tuple(self.clients):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait(message)
                except asyncio.QueueEmpty:
                    pass

    def snapshot(self) -> dict[str, Any]:
        return {
            "type": "snapshot",
            "run_id": next(reversed(self.runs), None) if self.runs else None,
            "seq": self._seq,
            "sim_ts": max((run.sim_ts for run in self.runs.values()), default=0),
            "payload": {
                "runs": [
                    {
                        "run_id": run.run_id,
                        "scenario": run.scenario,
                        "seed": run.seed,
                        "status": run.status,
                        "sim_ts": run.sim_ts,
                        "health": run.health,
                        "incident": run.incident.model_dump(mode="json") if run.incident else None,
                        "prediction": (
                            run.prediction.model_dump(mode="json") if run.prediction else None
                        ),
                        "verification": run.verification.model_dump(mode="json")
                        if run.verification
                        else None,
                    }
                    for run in self.runs.values()
                ]
            },
        }
