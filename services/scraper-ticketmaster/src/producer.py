"""Kafka producer for events.discovered (Phase 4: DB writes moved to the deduper)."""

import json

from aiokafka import AIOKafkaProducer
from opentelemetry import trace
from opentelemetry.propagate import inject

from src.parser import ParsedEvent

EVENTS_DISCOVERED_TOPIC = "events.discovered"
SOURCE = "ticketmaster"

tracer = trace.get_tracer("scraper-ticketmaster")


class DiscoveredEventProducer:
    """Publishes parsed events to events.discovered, keyed by source:external_id."""

    def __init__(self, bootstrap_servers: str) -> None:
        self._producer = AIOKafkaProducer(bootstrap_servers=bootstrap_servers)

    async def start(self) -> None:
        """Connect the underlying Kafka producer."""
        await self._producer.start()

    async def stop(self) -> None:
        """Flush and disconnect the underlying Kafka producer."""
        await self._producer.stop()

    async def publish(self, event: ParsedEvent) -> None:
        """Publish one discovered event with W3C trace context in the message headers."""
        key = f"{SOURCE}:{event.external_id}".encode()
        payload = {"source": SOURCE, **event.model_dump(mode="json")}
        with tracer.start_as_current_span(
            f"publish {EVENTS_DISCOVERED_TOPIC}", kind=trace.SpanKind.PRODUCER
        ):
            carrier: dict[str, str] = {}
            inject(carrier)
            headers = [(name, value.encode()) for name, value in carrier.items()]
            await self._producer.send_and_wait(
                EVENTS_DISCOVERED_TOPIC,
                json.dumps(payload).encode(),
                key=key,
                headers=headers,
            )
