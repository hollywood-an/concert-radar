"""Kafka producer for matches.proposed."""

from aiokafka import AIOKafkaProducer
from opentelemetry import trace
from opentelemetry.propagate import inject

from src.schemas import MatchProposed

MATCHES_PROPOSED_TOPIC = "matches.proposed"

tracer = trace.get_tracer("matcher")


class MatcherProducer:
    """Publishes proposed matches, keyed by user_uuid:event_uuid."""

    def __init__(self, bootstrap_servers: str) -> None:
        self._producer = AIOKafkaProducer(bootstrap_servers=bootstrap_servers)

    async def start(self) -> None:
        """Connect the underlying Kafka producer."""
        await self._producer.start()

    async def stop(self) -> None:
        """Flush and disconnect the underlying Kafka producer."""
        await self._producer.stop()

    async def publish_match(self, match: MatchProposed) -> None:
        """Send one match with W3C trace context in the message headers."""
        with tracer.start_as_current_span(
            f"publish {MATCHES_PROPOSED_TOPIC}", kind=trace.SpanKind.PRODUCER
        ):
            carrier: dict[str, str] = {}
            inject(carrier)
            headers = [(name, value.encode()) for name, value in carrier.items()]
            await self._producer.send_and_wait(
                MATCHES_PROPOSED_TOPIC,
                match.model_dump_json().encode(),
                key=f"{match.user_id}:{match.event_id}".encode(),
                headers=headers,
            )
