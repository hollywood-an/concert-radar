"""Kafka producer for events.deduped and events.status_changed."""

from aiokafka import AIOKafkaProducer
from opentelemetry import trace
from opentelemetry.propagate import inject
from pydantic import BaseModel

from src.schemas import DedupedEvent, StatusChange

EVENTS_DEDUPED_TOPIC = "events.deduped"
EVENTS_STATUS_CHANGED_TOPIC = "events.status_changed"

tracer = trace.get_tracer("deduper")


class DeduperProducer:
    """Publishes dedup outcomes, keyed by the canonical event uuid."""

    def __init__(self, bootstrap_servers: str) -> None:
        self._producer = AIOKafkaProducer(bootstrap_servers=bootstrap_servers)

    async def start(self) -> None:
        """Connect the underlying Kafka producer."""
        await self._producer.start()

    async def stop(self) -> None:
        """Flush and disconnect the underlying Kafka producer."""
        await self._producer.stop()

    async def publish_deduped(self, event: DedupedEvent) -> None:
        """Publish the canonical row a discovery resolved to."""
        await self._publish(EVENTS_DEDUPED_TOPIC, str(event.event_id), event)

    async def publish_status_changed(self, change: StatusChange) -> None:
        """Publish a real status transition on an existing event."""
        await self._publish(EVENTS_STATUS_CHANGED_TOPIC, str(change.event_id), change)

    async def _publish(self, topic: str, key: str, payload: BaseModel) -> None:
        """Send one message with W3C trace context in the message headers."""
        with tracer.start_as_current_span(f"publish {topic}", kind=trace.SpanKind.PRODUCER):
            carrier: dict[str, str] = {}
            inject(carrier)
            headers = [(name, value.encode()) for name, value in carrier.items()]
            await self._producer.send_and_wait(
                topic,
                payload.model_dump_json().encode(),
                key=key.encode(),
                headers=headers,
            )
