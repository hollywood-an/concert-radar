"""Kafka producer for events.enriched."""

from aiokafka import AIOKafkaProducer
from opentelemetry import trace
from opentelemetry.propagate import inject

from src.schemas import EnrichedEvent

EVENTS_ENRICHED_TOPIC = "events.enriched"

tracer = trace.get_tracer("enricher")


class EnricherProducer:
    """Publishes enrichment outcomes, keyed by the canonical event uuid."""

    def __init__(self, bootstrap_servers: str) -> None:
        self._producer = AIOKafkaProducer(bootstrap_servers=bootstrap_servers)

    async def start(self) -> None:
        """Connect the underlying Kafka producer."""
        await self._producer.start()

    async def stop(self) -> None:
        """Flush and disconnect the underlying Kafka producer."""
        await self._producer.stop()

    async def publish_enriched(self, event: EnrichedEvent) -> None:
        """Send one message with W3C trace context in the message headers."""
        with tracer.start_as_current_span(
            f"publish {EVENTS_ENRICHED_TOPIC}", kind=trace.SpanKind.PRODUCER
        ):
            carrier: dict[str, str] = {}
            inject(carrier)
            headers = [(name, value.encode()) for name, value in carrier.items()]
            await self._producer.send_and_wait(
                EVENTS_ENRICHED_TOPIC,
                event.model_dump_json().encode(),
                key=str(event.event_id).encode(),
                headers=headers,
            )
