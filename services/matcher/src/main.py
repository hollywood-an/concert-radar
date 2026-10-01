"""Long-running consumer: events.enriched + users.taste_updated -> matches.proposed."""

import asyncio

import structlog
from aiokafka import AIOKafkaConsumer, ConsumerRecord
from opentelemetry import trace
from opentelemetry.propagate import extract
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.config import Settings
from src.producer import MatcherProducer
from src.ranker import matches_for_event, matches_for_followed_artists
from src.schemas import EnrichedEvent, TasteUpdated
from src.telemetry import setup_telemetry

SERVICE_NAME = "matcher"
EVENTS_ENRICHED_TOPIC = "events.enriched"
USERS_TASTE_UPDATED_TOPIC = "users.taste_updated"

logger = structlog.get_logger()
tracer = trace.get_tracer(SERVICE_NAME)


def main() -> None:
    """Configure telemetry and run the consumer until interrupted."""
    provider = setup_telemetry(SERVICE_NAME)
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("shutting down")
    finally:
        provider.shutdown()


async def run(stop_after: int | None = None) -> int:
    """Consume both matcher topics until stopped; return the number of messages processed."""
    settings = Settings()
    engine = create_async_engine(settings.database_url)
    consumer = AIOKafkaConsumer(
        EVENTS_ENRICHED_TOPIC,
        USERS_TASTE_UPDATED_TOPIC,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=SERVICE_NAME,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    producer = MatcherProducer(settings.kafka_bootstrap_servers)
    await consumer.start()
    await producer.start()
    try:
        logger.info("consuming", topics=[EVENTS_ENRICHED_TOPIC, USERS_TASTE_UPDATED_TOPIC])
        return await consume_loop(consumer, producer, engine, stop_after)
    finally:
        await consumer.stop()
        await producer.stop()
        await engine.dispose()


async def consume_loop(
    consumer: AIOKafkaConsumer,
    producer: MatcherProducer,
    engine: AsyncEngine,
    stop_after: int | None = None,
) -> int:
    """Process messages one at a time, committing offsets after each successful handle."""
    processed = 0
    async for message in consumer:
        try:
            await handle_message(message, producer, engine)
        except ValidationError:
            # A malformed message can never succeed; skip it after logging so the
            # partition does not wedge. Anything else propagates and crashes the
            # process, leaving the offset uncommitted for a clean retry.
            logger.exception(
                "skipping malformed message", topic=message.topic, offset=message.offset
            )
        await consumer.commit()
        processed += 1
        if stop_after is not None and processed >= stop_after:
            break
    return processed


async def handle_message(
    message: ConsumerRecord, producer: MatcherProducer, engine: AsyncEngine
) -> None:
    """Match one enriched event or taste update, continuing the producer's trace."""
    context = extract({name: value.decode() for name, value in message.headers})
    with tracer.start_as_current_span(
        f"consume {message.topic}", context=context, kind=trace.SpanKind.CONSUMER
    ):
        if message.topic == EVENTS_ENRICHED_TOPIC:
            enriched = EnrichedEvent.model_validate_json(message.value)
            # Only a newly announced show alerts; re-scrapes of known shows stay quiet.
            matches = await matches_for_event(engine, enriched.event_id) if enriched.is_new else []
            subject = {"event_id": str(enriched.event_id), "is_new": enriched.is_new}
        else:
            taste = TasteUpdated.model_validate_json(message.value)
            matches = await matches_for_followed_artists(
                engine, taste.user_id, taste.followed_artist_ids
            )
            subject = {"user_id": str(taste.user_id)}
        for match in matches:
            await producer.publish_match(match)
        logger.info("matches proposed", topic=message.topic, count=len(matches), **subject)


if __name__ == "__main__":
    main()
