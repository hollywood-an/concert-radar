"""Long-running consumer: events.discovered -> Postgres -> events.deduped."""

import asyncio

import structlog
from aiokafka import AIOKafkaConsumer, ConsumerRecord
from opentelemetry import trace
from opentelemetry.propagate import extract
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.config import Settings
from src.handler import process_discovered
from src.producer import DeduperProducer
from src.schemas import DedupedEvent, DiscoveredEvent, StatusChange
from src.telemetry import setup_telemetry

SERVICE_NAME = "deduper"
EVENTS_DISCOVERED_TOPIC = "events.discovered"

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
    """Consume events.discovered until stopped; return the number of messages processed."""
    settings = Settings()
    engine = create_async_engine(settings.database_url)
    consumer = AIOKafkaConsumer(
        EVENTS_DISCOVERED_TOPIC,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=SERVICE_NAME,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    producer = DeduperProducer(settings.kafka_bootstrap_servers)
    await consumer.start()
    await producer.start()
    try:
        logger.info("consuming", topic=EVENTS_DISCOVERED_TOPIC)
        return await consume_loop(consumer, producer, engine, stop_after)
    finally:
        await consumer.stop()
        await producer.stop()
        await engine.dispose()


async def consume_loop(
    consumer: AIOKafkaConsumer,
    producer: DeduperProducer,
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
            # partition does not wedge. Anything else (DB down, broker gone) propagates
            # and crashes the process, leaving the offset uncommitted for a clean retry.
            logger.exception("skipping malformed message", offset=message.offset)
        await consumer.commit()
        processed += 1
        if stop_after is not None and processed >= stop_after:
            break
    return processed


async def handle_message(
    message: ConsumerRecord, producer: DeduperProducer, engine: AsyncEngine
) -> None:
    """Dedupe one discovered event and publish the outcome, continuing the producer's trace."""
    context = extract({name: value.decode() for name, value in message.headers})
    with tracer.start_as_current_span(
        f"consume {EVENTS_DISCOVERED_TOPIC}", context=context, kind=trace.SpanKind.CONSUMER
    ):
        event = DiscoveredEvent.model_validate_json(message.value)
        result = await process_discovered(engine, event)
        await producer.publish_deduped(
            DedupedEvent(
                event_id=result.event_id,
                venue_id=result.venue_id,
                artist_ids=result.artist_ids,
                source=event.source,
                external_id=event.external_id,
                title=event.title,
                starts_at=event.starts_at,
                status=event.status,
                is_new=result.is_new,
            )
        )
        if result.old_status is not None:
            await producer.publish_status_changed(
                StatusChange(
                    event_id=result.event_id,
                    source=event.source,
                    external_id=event.external_id,
                    old_status=result.old_status,
                    new_status=event.status,
                )
            )
        logger.info(
            "event deduped",
            event_id=str(result.event_id),
            source=event.source,
            external_id=event.external_id,
            is_new=result.is_new,
            merged_cross_source=result.merged_cross_source,
        )


if __name__ == "__main__":
    main()
