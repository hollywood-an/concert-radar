"""Kafka producer publishing users.taste_updated after follow changes.

Publishing is best-effort: the follow is already committed to Postgres, so a broker
outage degrades downstream matching freshness rather than failing the request.
"""

import asyncio
import json
from functools import lru_cache
from uuid import UUID

import structlog
from aiokafka import AIOKafkaProducer
from opentelemetry import trace
from opentelemetry.propagate import inject

from src.config import get_settings

USERS_TASTE_UPDATED_TOPIC = "users.taste_updated"

logger = structlog.get_logger()
tracer = trace.get_tracer("gateway")


class TasteUpdatedPublisher:
    """Lazily-connected producer keyed by user uuid."""

    def __init__(self) -> None:
        self._producer: AIOKafkaProducer | None = None
        self._lock = asyncio.Lock()

    async def _get_producer(self) -> AIOKafkaProducer:
        """Connect on first use so the app boots (and tests run) without a broker."""
        async with self._lock:
            if self._producer is None:
                producer = AIOKafkaProducer(
                    bootstrap_servers=get_settings().kafka_bootstrap_servers
                )
                await producer.start()
                self._producer = producer
            return self._producer

    async def publish(self, user_id: UUID) -> None:
        """Publish that the user's taste embedding changed; log and continue on failure."""
        try:
            producer = await self._get_producer()
            with tracer.start_as_current_span(
                f"publish {USERS_TASTE_UPDATED_TOPIC}", kind=trace.SpanKind.PRODUCER
            ):
                carrier: dict[str, str] = {}
                inject(carrier)
                headers = [(name, value.encode()) for name, value in carrier.items()]
                await producer.send_and_wait(
                    USERS_TASTE_UPDATED_TOPIC,
                    json.dumps({"user_id": str(user_id)}).encode(),
                    key=str(user_id).encode(),
                    headers=headers,
                )
        except Exception:
            logger.exception("failed to publish users.taste_updated", user_id=str(user_id))

    async def stop(self) -> None:
        """Flush and disconnect, if a producer was ever started."""
        async with self._lock:
            if self._producer is not None:
                await self._producer.stop()
                self._producer = None


@lru_cache
def get_taste_publisher() -> TasteUpdatedPublisher:
    """Return the process-wide publisher instance."""
    return TasteUpdatedPublisher()
