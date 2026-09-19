"""Redpanda access helpers."""

import asyncio
import json
from collections.abc import AsyncIterator

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

TOPIC_EVENTS = "kea.events.raw"
TOPIC_UPDATES = "kea.engine.updates"


async def ping(bootstrap: str, timeout: float = 3.0) -> bool:
    producer = AIOKafkaProducer(bootstrap_servers=bootstrap)
    try:
        await asyncio.wait_for(producer.start(), timeout)
        return True
    except Exception:
        return False
    finally:
        try:
            await asyncio.wait_for(producer.stop(), timeout)
        except Exception:
            pass


async def publish(bootstrap: str, topic: str, value: object, key: str | None = None) -> None:
    producer = AIOKafkaProducer(bootstrap_servers=bootstrap)
    await producer.start()
    try:
        await producer.send_and_wait(
            topic,
            json.dumps(value, separators=(",", ":"), sort_keys=True).encode(),
            key=key.encode() if key else None,
        )
    finally:
        await producer.stop()


async def publish_many(bootstrap: str, topic: str, values: list[tuple[object, str | None]]) -> None:
    producer = AIOKafkaProducer(bootstrap_servers=bootstrap)
    await producer.start()
    try:
        for value, key in values:
            await producer.send_and_wait(
                topic,
                json.dumps(value, separators=(",", ":"), sort_keys=True).encode(),
                key=key.encode() if key else None,
            )
    finally:
        await producer.stop()


async def consume(
    bootstrap: str, topic: str, group_id: str, auto_offset_reset: str = "latest"
) -> AsyncIterator[dict[str, object]]:
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=bootstrap,
        group_id=group_id,
        auto_offset_reset=auto_offset_reset,
        enable_auto_commit=True,
    )
    started = False
    try:
        await consumer.start()
        started = True
        async for message in consumer:
            yield json.loads(message.value)
    finally:
        if started:
            await consumer.stop()
