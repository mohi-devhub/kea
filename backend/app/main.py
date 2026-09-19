"""FastAPI application, live simulator controls, and read-side materialized views."""

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from app.api.store import RunStore, RunView
from app.config import ROOT, get_settings
from app.engine.prediction import make_prediction, verify_prediction
from app.graph import client as graph
from app.models.api import (
    HealthResponse,
    ScenarioInfo,
    ServiceNode,
    SimulateRequest,
    TopologyEdge,
    TopologyResponse,
)
from app.models.events import Event
from app.simulator.generator import EPOCH_MS, generate
from app.simulator.loader import load_scenarios
from app.simulator.publisher import publish_events
from app.stream import kafka
from app.stream.worker import Worker

EVENT_ADAPTER: TypeAdapter[Event] = TypeAdapter(Event)


async def _raw_reader(app: FastAPI) -> None:
    async for raw in kafka.consume(
        app.state.settings.kafka_bootstrap, kafka.TOPIC_EVENTS, "kea-api-view"
    ):
        try:
            event = EVENT_ADAPTER.validate_python(raw)
        except ValidationError:
            continue
        if event.run_id in app.state.store.retired_runs:
            continue
        app.state.store.record_event(event)
        message_type = {
            "log": "log.batch",
            "deployment": "deployment.observed",
            "rollback": "deployment.observed",
        }.get(event.kind)
        if message_type is None:
            continue
        await app.state.store.broadcast(
            {
                "type": message_type,
                "run_id": event.run_id,
                "seq": event.seq,
                "sim_ts": event.ts,
                "payload": [event.model_dump(mode="json")]
                if message_type.endswith("batch")
                else event.model_dump(mode="json"),
            }
        )


async def _metric_flusher(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(0.25)
        await app.state.store.flush_metrics()


async def _update_reader(app: FastAPI) -> None:
    async for raw in kafka.consume(
        app.state.settings.kafka_bootstrap, kafka.TOPIC_UPDATES, "kea-api-updates"
    ):
        await app.state.store.update(raw)
        if raw.get("type") != "incident_resolved":
            continue
        run_id = str(raw.get("run_id"))
        view = app.state.store.runs.get(run_id)
        if view is None or view.prediction is None or view.verification is not None:
            continue
        incident = view.incident
        if incident is None:
            continue
        actual_health = dict(incident.service_health)
        actual_health.update(view.health)
        verification = verify_prediction(
            view.prediction,
            actual_health,
            int(str(raw.get("sim_ts", view.sim_ts))),
        )
        view.verification = verification
        await app.state.store.broadcast(
            {
                "type": "prediction.verified",
                "run_id": run_id,
                "seq": int(str(raw.get("seq", 0))),
                "sim_ts": int(str(raw.get("sim_ts", view.sim_ts))),
                "payload": verification.model_dump(mode="json"),
            }
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.settings = settings
    app.state.topology = graph.load_topology(settings.topology_path)
    app.state.driver = graph.make_driver(settings)
    app.state.store = RunStore()
    app.state.stop_events = {}
    app.state.run_tasks = {}
    app.state.run_meta = {}
    app.state.tasks = []
    if await graph.ping(app.state.driver):
        await graph.init_schema(app.state.driver)
        await graph.seed_topology(app.state.driver, app.state.topology)
    if settings.run_worker_in_api:
        worker = Worker(settings.kafka_bootstrap, str(settings.topology_path), app.state.driver)
        app.state.worker = worker
        app.state.tasks.append(asyncio.create_task(worker.run()))
    else:
        app.state.worker = None
    app.state.tasks.append(asyncio.create_task(_metric_flusher(app)))
    for reader in (_raw_reader(app), _update_reader(app)):
        app.state.tasks.append(asyncio.create_task(reader))
    try:
        yield
    finally:
        for event in app.state.stop_events.values():
            event.set()
        for task in app.state.run_tasks.values():
            task.cancel()
        for task in app.state.tasks:
            task.cancel()
        for task in app.state.tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await app.state.store.flush_metrics(force=True)
        await app.state.driver.close()


def create_app() -> FastAPI:
    app = FastAPI(title="kea", lifespan=lifespan)

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 409: "CONFLICT", 422: "INVALID"}.get(exc.status_code, "ERROR")
        return JSONResponse(
            {"error": {"code": code, "message": str(exc.detail)}}, status_code=exc.status_code
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(part) for part in first.get("loc", ()))
        message = f"{where}: {first.get('msg', 'invalid request')}"
        return JSONResponse(
            {"error": {"code": "VALIDATION_ERROR", "message": message}}, status_code=422
        )

    def start_publisher(run_id: str) -> None:
        """(Re)start paced publishing of the run's remaining events."""
        meta = app.state.run_meta[run_id]
        stop_event = asyncio.Event()
        app.state.stop_events[run_id] = stop_event
        scenario = meta["scenario"]

        async def run_publisher() -> None:
            try:
                await publish_events(
                    app.state.settings.kafka_bootstrap,
                    meta["events"],
                    EPOCH_MS + scenario.warmup_s * 1000,
                    meta["speed"],
                    app.state.settings.sim_warmup_speed,
                    stop_event,
                    meta["progress"],
                    meta["skip_warmup"],
                )
            finally:
                view = app.state.store.runs.get(run_id)
                if view is not None and not stop_event.is_set():
                    view.status = "completed"
                    await app.state.store.broadcast(
                        {
                            "type": "run.stopped",
                            "run_id": run_id,
                            "seq": 0,
                            "sim_ts": view.sim_ts,
                            "payload": {"status": "completed"},
                        }
                    )

        app.state.run_tasks[run_id] = asyncio.create_task(run_publisher())

    @app.get("/health")
    async def health() -> HealthResponse:
        k = await kafka.ping(app.state.settings.kafka_bootstrap)
        n = await graph.ping(app.state.driver)
        return HealthResponse(status="ok" if k and n else "degraded", kafka=k, neo4j=n)

    @app.get("/topology")
    async def topology() -> TopologyResponse:
        t = app.state.topology
        latest = (
            app.state.store.runs[next(reversed(app.state.store.runs))]
            if app.state.store.runs
            else None
        )
        return TopologyResponse(
            services=[
                ServiceNode(
                    name=name,
                    kind=definition.kind,
                    tier=definition.tier,
                    layout=definition.layout,
                    customer_facing=definition.tier == "customer_facing",
                    health=latest.health.get(name, "healthy") if latest else "healthy",
                )
                for name, definition in t.services.items()
            ],
            edges=[
                TopologyEdge(source=edge.from_, target=edge.to, blocking=edge.blocking)
                for edge in t.edges
            ],
        )

    @app.get("/scenarios")
    async def scenarios() -> list[ScenarioInfo]:
        return [
            ScenarioInfo(
                id=scenario.id,
                title=scenario.title,
                description=scenario.description,
                priority=scenario.priority,
                fix_flow_available=any(
                    deployment.commit_ref == "deploy-182" for deployment in scenario.deployments
                ),
            )
            for scenario in load_scenarios(ROOT / "scenarios", app.state.topology)
        ]

    @app.post("/simulate/{scenario}")
    async def simulate(scenario: str, request: SimulateRequest) -> dict[str, str]:
        scenarios_by_id = {
            item.id: item for item in load_scenarios(ROOT / "scenarios", app.state.topology)
        }
        if scenario not in scenarios_by_id:
            raise HTTPException(status_code=404, detail="unknown scenario")
        speed = request.speed or app.state.settings.sim_speed_default
        run_id = f"{scenario}-{request.seed}-{uuid.uuid4().hex[:8]}"
        app.state.store.create(run_id, scenario, request.seed, speed)
        await app.state.store.broadcast(
            {
                "type": "run.started",
                "run_id": run_id,
                "seq": 0,
                "sim_ts": 0,
                "payload": {"scenario": scenario, "seed": request.seed, "speed": speed},
            }
        )

        events = generate(scenarios_by_id[scenario], app.state.topology, request.seed, run_id)
        app.state.run_meta[run_id] = {
            "scenario": scenarios_by_id[scenario],
            "seed": request.seed,
            "speed": speed,
            "skip_warmup": request.skip_warmup,
            "events": events,
            "progress": {"next": 0},
        }
        start_publisher(run_id)
        return {"run_id": run_id}

    @app.post("/events")
    async def events(event: Event) -> dict[str, str]:
        if event.service not in app.state.topology.services:
            raise HTTPException(status_code=422, detail="unknown service")
        await kafka.publish(
            app.state.settings.kafka_bootstrap,
            kafka.TOPIC_EVENTS,
            event.model_dump(mode="json"),
            event.service,
        )
        return {"event_id": event.event_id}

    @app.get("/runs/{run_id}")
    async def run(run_id: str) -> dict[str, object]:
        view = app.state.store.runs.get(run_id)
        if view is None:
            raise HTTPException(status_code=404, detail="run not found")
        return {
            "run_id": view.run_id,
            "scenario": view.scenario,
            "seed": view.seed,
            "speed": view.speed,
            "status": view.status,
            "sim_ts": view.sim_ts,
        }

    @app.post("/runs/{run_id}/stop")
    async def stop(run_id: str) -> dict[str, str]:
        if run_id not in app.state.stop_events:
            raise HTTPException(status_code=404, detail="run not found")
        app.state.stop_events[run_id].set()
        task = app.state.run_tasks.pop(run_id, None)
        if task is not None:
            task.cancel()
        app.state.store.runs[run_id].status = "stopped"
        await app.state.store.broadcast(
            {
                "type": "run.stopped",
                "run_id": run_id,
                "seq": 0,
                "sim_ts": app.state.store.runs[run_id].sim_ts,
                "payload": {},
            }
        )
        return {"run_id": run_id}

    @app.post("/runs/{run_id}/recover")
    async def recover(run_id: str) -> dict[str, object]:
        view = app.state.store.runs.get(run_id)
        meta = app.state.run_meta.get(run_id)
        if view is None or meta is None:
            raise HTTPException(status_code=404, detail="run not found")
        scenario = meta["scenario"]
        if scenario.recover is None:
            raise HTTPException(status_code=409, detail="scenario has no recovery")
        app.state.stop_events[run_id].set()
        task = app.state.run_tasks.pop(run_id, None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        nxt = meta["progress"]["next"]
        if nxt == 0:
            raise HTTPException(status_code=409, detail="run has not started publishing")
        last_ts = meta["events"][nxt - 1].ts
        recover_s = -(-(last_ts - EPOCH_MS) // 1000) - scenario.warmup_s + 1  # ceil, then past it
        if recover_s < 0:
            raise HTTPException(status_code=409, detail="run is still warming up")
        if view.incident is not None and view.prediction is None:
            prediction = make_prediction(view.incident, view.sim_ts)
            view.prediction = prediction
            await app.state.store.broadcast(
                {
                    "type": "prediction.made",
                    "run_id": run_id,
                    "seq": view.incident.revision,
                    "sim_ts": view.sim_ts,
                    "payload": prediction.model_dump(mode="json"),
                }
            )
        meta["events"] = generate(
            scenario, app.state.topology, meta["seed"], run_id, recover_at_s=recover_s
        )
        start_publisher(run_id)
        return {"run_id": run_id, "recover_at_s": recover_s}

    @app.get("/incidents/{incident_id}/prediction")
    async def prediction(incident_id: str) -> dict[str, object]:
        """Frozen prediction after Recover; before that, a live preview (`frozen: false`)."""
        view = find_incident(incident_id)
        if view is None or view.incident is None:
            raise HTTPException(status_code=404, detail="incident not found")
        frozen = view.prediction is not None
        if view.prediction is not None:
            current = view.prediction
        elif view.incident.candidates:
            current = make_prediction(view.incident, view.sim_ts)
        else:
            raise HTTPException(status_code=404, detail="prediction not available")
        return {
            **current.model_dump(mode="json"),
            "frozen": frozen,
            "verification": (
                view.verification.model_dump(mode="json") if view.verification else None
            ),
        }

    @app.post("/reset")
    async def reset() -> dict[str, str]:
        retired = set(app.state.store.runs)
        app.state.store.retired_runs.update(retired)
        if app.state.worker is not None:
            await app.state.worker.pause_and_retire(retired)
        for event in app.state.stop_events.values():
            event.set()
        for task in app.state.run_tasks.values():
            task.cancel()
        app.state.stop_events.clear()
        app.state.run_tasks.clear()
        app.state.run_meta.clear()
        await app.state.store.flush_metrics(force=True)
        app.state.store.runs.clear()
        await graph.reset_runs(app.state.driver)
        await graph.seed_topology(app.state.driver, app.state.topology)
        if app.state.worker is not None:
            app.state.worker.resume()
        return {"status": "ok"}

    @app.get("/incidents")
    async def incidents() -> list[dict[str, object]]:
        return [
            view.incident.model_dump(mode="json")
            for view in app.state.store.runs.values()
            if view.incident
        ]

    @app.get("/incidents/{incident_id}")
    async def incident(incident_id: str) -> dict[str, object]:
        for view in app.state.store.runs.values():
            if view.incident and view.incident.incident_id == incident_id:
                return dict(view.incident.model_dump(mode="json"))
        raise HTTPException(status_code=404, detail="incident not found")

    def find_incident(incident_id: str) -> RunView | None:
        store: RunStore = app.state.store
        for view in store.runs.values():
            if view.incident and view.incident.incident_id == incident_id:
                return view
        return None

    @app.get("/incidents/{incident_id}/timeline")
    async def timeline(incident_id: str) -> list[dict[str, object]]:
        view = find_incident(incident_id)
        if view is None:
            raise HTTPException(status_code=404, detail="incident not found")
        items: list[dict[str, object]] = []
        for event in view.events:
            if event.kind in {"deployment", "rollback", "log"}:
                items.append(
                    {
                        "type": event.kind,
                        "ts": event.ts,
                        "service": event.service,
                        "payload": event.model_dump(mode="json"),
                    }
                )
        for update in view.updates:
            items.append(
                {
                    "type": update.get("type"),
                    "ts": update.get("sim_ts", 0),
                    "payload": update.get("payload", {}),
                }
            )
        return sorted(items, key=lambda item: (int(str(item["ts"])), str(item["type"])))

    @app.get("/incidents/{incident_id}/causal-path")
    async def causal_path(incident_id: str, candidate: str) -> dict[str, object]:
        view = find_incident(incident_id)
        if view is None or view.incident is None:
            raise HTTPException(status_code=404, detail="incident not found")
        selected = next(
            (item for item in view.incident.candidates if item.candidate_id == candidate), None
        )
        if selected is None:
            raise HTTPException(status_code=404, detail="candidate not found")
        return {
            "incident_id": incident_id,
            "candidate_id": candidate,
            "chain": [item.model_dump(mode="json") for item in selected.chain],
            "covered_anomaly_ids": selected.covered_anomaly_ids,
        }

    @app.get("/incidents/{incident_id}/blast-radius")
    async def blast_radius(incident_id: str) -> dict[str, object]:
        view = find_incident(incident_id)
        if view is None or view.incident is None:
            raise HTTPException(status_code=404, detail="incident not found")
        top = view.incident.candidates[0].service if view.incident.candidates else None
        callers = await graph.blast_callers(app.state.driver, top) if top else []
        return {
            **view.incident.blast_radius.model_dump(mode="json"),
            "root_service": top,
            "callers": callers,  # live Neo4j result: who reaches the root via blocking calls
            "cypher": graph.BLAST_CYPHER,
            "parameters": {"service": top},
        }

    @app.get("/services/{name}")
    async def service_detail(name: str) -> dict[str, object]:
        definition = app.state.topology.services.get(name)
        if definition is None:
            raise HTTPException(status_code=404, detail="service not found")
        latest = next(reversed(app.state.store.runs), None)
        view = app.state.store.runs[latest] if latest else None
        metrics = (
            []
            if view is None
            else [
                point
                for (service, _), points in view.metrics.items()
                if service == name
                for point in points
            ]
        )
        return {
            "name": name,
            "kind": definition.kind,
            "tier": definition.tier,
            "health": view.health.get(name, "healthy") if view else "healthy",
            "metrics": metrics[-100:],
        }

    @app.get("/graph/{service}")
    async def graph_view(
        service: str, direction: str = "downstream", depth: int = 3
    ) -> dict[str, object]:
        if service not in app.state.topology.services:
            raise HTTPException(status_code=404, detail="service not found")
        if direction not in {"upstream", "downstream"} or not 1 <= depth <= 8:
            raise HTTPException(status_code=422, detail="invalid graph traversal")
        return {
            "service": service,
            "direction": direction,
            "depth": depth,
            "nodes": await graph.traverse(app.state.driver, service, direction, depth),
        }

    @app.get("/runs/{run_id}/metrics")
    async def metrics(
        run_id: str, service: str | None = None, metric: str | None = None
    ) -> list[dict[str, object]]:
        view = app.state.store.runs.get(run_id)
        if view is None:
            raise HTTPException(status_code=404, detail="run not found")
        return [
            point
            for (point_service, point_metric), points in view.metrics.items()
            if (service is None or service == point_service)
            and (metric is None or metric == point_metric)
            for point in points
        ]

    @app.websocket("/ws")
    async def websocket(socket: WebSocket) -> None:
        await socket.accept()
        queue = await app.state.store.subscribe()
        try:
            await socket.send_json(app.state.store.snapshot())
            while True:
                await socket.send_json(await queue.get())
        except WebSocketDisconnect:
            pass
        finally:
            app.state.store.unsubscribe(queue)

    return app


app = create_app()
