"""Redpanda access helpers."""

import asyncio

from aiokafka import AIOKafkaProducer

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
