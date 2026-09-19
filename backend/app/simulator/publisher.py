"""Paced simulator publisher used by POST /simulate and /runs/{id}/recover."""

import asyncio
import json

from aiokafka import AIOKafkaProducer

from app.models.events import Event
from app.stream.kafka import TOPIC_EVENTS


async def publish_events(
    bootstrap: str,
    events: list[Event],
    warmup_end_ts: int,
    speed: float,
    warmup_speed: float,
    stop_event: asyncio.Event,
    progress: dict[str, int],
    skip_warmup: bool = False,
) -> None:
    """Publish `events[progress["next"]:]` paced by simulated time; updates `progress["next"]`.

    `progress` lets the API resume the same run with a recovery-modified tail (no seq gaps).
    """
    start = progress["next"]
    previous_ts: int | None = events[start - 1].ts if start > 0 else None
    producer = AIOKafkaProducer(bootstrap_servers=bootstrap)
    await producer.start()
    try:
        for index in range(start, len(events)):
            event = events[index]
            if stop_event.is_set():
                break
            if previous_ts is not None and not (skip_warmup and event.ts < warmup_end_ts):
                sim_delta = max(0, event.ts - previous_ts) / 1000
                rate = warmup_speed if event.ts < warmup_end_ts else speed
                await asyncio.sleep(sim_delta / max(rate, 0.01))
            await producer.send_and_wait(
                TOPIC_EVENTS,
                json.dumps(
                    event.model_dump(mode="json"), separators=(",", ":"), sort_keys=True
                ).encode(),
                key=event.service.encode(),
            )
            progress["next"] = index + 1
            previous_ts = event.ts
    finally:
        await producer.stop()
