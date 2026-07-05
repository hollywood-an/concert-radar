"""Kafka producer for notifications.sent."""

from aiokafka import AIOKafkaProducer
from opentelemetry import trace
from opentelemetry.propagate import inject

from src.schemas import NotificationSent

NOTIFICATIONS_SENT_TOPIC = "notifications.sent"

tracer = trace.get_tracer("notifier")


class NotifierProducer:
    """Publishes sent notifications, keyed by user_uuid:event_uuid."""

    def __init__(self, bootstrap_servers: str) -> None:
        self._producer = AIOKafkaProducer(bootstrap_servers=bootstrap_servers)

    async def start(self) -> None:
        """Connect the underlying Kafka producer."""
        await self._producer.start()

    async def stop(self) -> None:
        """Flush and disconnect the underlying Kafka producer."""
        await self._producer.stop()

    async def publish_sent(self, notification: NotificationSent) -> None:
        """Send one notification record with W3C trace context in the message headers."""
        with tracer.start_as_current_span(
            f"publish {NOTIFICATIONS_SENT_TOPIC}", kind=trace.SpanKind.PRODUCER
        ):
            carrier: dict[str, str] = {}
            inject(carrier)
            headers = [(name, value.encode()) for name, value in carrier.items()]
            await self._producer.send_and_wait(
                NOTIFICATIONS_SENT_TOPIC,
                notification.model_dump_json().encode(),
                key=f"{notification.user_id}:{notification.event_id}".encode(),
                headers=headers,
            )
