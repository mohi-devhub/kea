"""Kafka worker: validate, deduplicate, run the pure engine, and publish updates."""

import asyncio
import logging

from neo4j import AsyncDriver
from pydantic import TypeAdapter, ValidationError

from app.config import get_settings
from app.engine import EngineState, InMemoryTopology
from app.graph import client as graph
from app.models.engine import EngineUpdate
from app.models.events import Event
from app.stream.kafka import TOPIC_EVENTS, TOPIC_UPDATES, consume, publish

logger = logging.getLogger(__name__)
EVENT_ADAPTER: TypeAdapter[Event] = TypeAdapter(Event)


class Worker:
    def __init__(
        self, bootstrap: str, topology_path: str, driver: AsyncDriver | None = None
    ) -> None:
        from pathlib import Path

        topology = graph.load_topology(Path(topology_path))
        self.bootstrap = bootstrap
        self.topology = InMemoryTopology(topology)
        self.driver = driver
        self.states: dict[str, EngineState] = {}
        self.seen: set[str] = set()
        self.invalid_events = 0
        self.duplicate_events = 0
        self.retired_runs: set[str] = set()
        self._lock = asyncio.Lock()
        self.paused = False

    def retire_runs(self, run_ids: set[str]) -> None:
        self.retired_runs.update(run_ids)
        for run_id in run_ids:
            self.states.pop(run_id, None)

    async def pause_and_retire(self, run_ids: set[str]) -> None:
        async with self._lock:
            self.paused = True
            self.retire_runs(run_ids)

    def resume(self) -> None:
        self.paused = False

    async def handle(self, raw: object) -> list[EngineUpdate]:
        async with self._lock:
            if self.paused:
                return []
            try:
                event = EVENT_ADAPTER.validate_python(raw)
            except ValidationError:
                self.invalid_events += 1
                return []
            if event.event_id in self.seen:
                self.duplicate_events += 1
                return []
            if event.run_id in self.retired_runs:
                return []
            if event.service not in self.topology.topology.services:
                self.invalid_events += 1
                return []
            self.seen.add(event.event_id)
            state = self.states.setdefault(event.run_id, EngineState(event.run_id, self.topology))
            updates = state.ingest(event)
            if self.driver is not None:
                await graph.write_event(self.driver, event)
                for update in updates:
                    await graph.write_engine_update(self.driver, update, state.incident)
            enriched: list[EngineUpdate] = []
            for update in updates:
                payload = dict(update.payload)
                if update.type.startswith("anomaly"):
                    anomaly_id = str(payload.get("anomaly_id"))
                    anomaly = next(
                        item for item in state.anomalies if item.anomaly_id == anomaly_id
                    )
                    payload = anomaly.model_dump(mode="json")
                elif state.incident is not None and update.type.startswith("incident"):
                    payload["incident"] = state.incident.model_dump(mode="json")
                enriched.append(update.model_copy(update={"payload": payload}))
            return enriched

    async def run(self) -> None:
        async for raw in consume(self.bootstrap, TOPIC_EVENTS, "kea-worker"):
            for update in await self.handle(raw):
                await publish(
                    self.bootstrap,
                    TOPIC_UPDATES,
                    update.model_dump(mode="json"),
                    update.run_id,
                )


async def main() -> None:
    settings = get_settings()
    driver = graph.make_driver(settings)
    if await graph.ping(driver):
        await graph.init_schema(driver)
        topology = graph.load_topology(settings.topology_path)
        await graph.seed_topology(driver, topology)
    worker = Worker(settings.kafka_bootstrap, str(settings.topology_path), driver)
    try:
        await worker.run()
    finally:
        await driver.close()


if __name__ == "__main__":
    asyncio.run(main())
