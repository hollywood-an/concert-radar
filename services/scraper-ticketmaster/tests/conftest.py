"""Shared fixtures: the saved API payload, a Redpanda container, and a trace-scoped reader."""

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from aiokafka import AIOKafkaConsumer
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from testcontainers.kafka import RedpandaContainer

from src.producer import EVENTS_DISCOVERED_TOPIC

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ticketmaster_columbus.json"


@pytest.fixture
def payload() -> dict[str, Any]:
    """Load the saved Discovery API fixture page."""
    data: dict[str, Any] = json.loads(FIXTURE_PATH.read_text())
    return data


@pytest.fixture(scope="session")
def kafka_bootstrap() -> Iterator[str]:
    """Start Redpanda in a container and yield its bootstrap server address."""
    with RedpandaContainer("docker.redpanda.com/redpandadata/redpanda:v24.1.1") as container:
        yield container.get_bootstrap_server()


@pytest.fixture(scope="session", autouse=True)
def _tracer_provider() -> None:
    """Install a real tracer provider so producer spans carry valid, injectable contexts."""
    trace.set_tracer_provider(TracerProvider())


async def consume_discovered(bootstrap: str, trace_id: str, count: int) -> list[Any]:
    """Read events.discovered from the start until `count` messages of trace `trace_id` arrive."""
    # Several tests publish the same fixture events to the shared broker, so a test finds its
    # own messages by trace id rather than by position in the topic.
    consumer = AIOKafkaConsumer(
        EVENTS_DISCOVERED_TOPIC, bootstrap_servers=bootstrap, auto_offset_reset="earliest"
    )
    await consumer.start()
    messages = []
    try:
        async with asyncio.timeout(10):
            async for message in consumer:
                traceparent = dict(message.headers).get("traceparent", b"").decode()
                if traceparent.startswith(f"00-{trace_id}-"):
                    messages.append(message)
                    if len(messages) == count:
                        break
    finally:
        await consumer.stop()
    return messages
