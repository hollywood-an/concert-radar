"""Long-running consumer: events.deduped -> MusicBrainz/Spotify/embeddings -> events.enriched."""

import asyncio

import structlog
from aiokafka import AIOKafkaConsumer, ConsumerRecord
from opentelemetry import trace
from opentelemetry.propagate import extract
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.config import Settings
from src.handler import process_deduped
from src.musicbrainz import MusicBrainzClient
from src.producer import EnricherProducer
from src.schemas import DedupedEvent, EnrichedEvent
from src.spotify import SpotifyClient
from src.telemetry import setup_telemetry

SERVICE_NAME = "enricher"
EVENTS_DEDUPED_TOPIC = "events.deduped"

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


async def run(
    stop_after: int | None = None,
    mb: MusicBrainzClient | None = None,
    spotify: SpotifyClient | None = None,
) -> int:
    """Consume events.deduped until stopped; return the number of messages processed."""
    settings = Settings()
    engine = create_async_engine(settings.database_url)
    mb = mb if mb is not None else MusicBrainzClient()
    spotify = (
        spotify
        if spotify is not None
        else SpotifyClient(settings.spotify_client_id, settings.spotify_client_secret)
    )
    consumer = AIOKafkaConsumer(
        EVENTS_DEDUPED_TOPIC,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=SERVICE_NAME,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    producer = EnricherProducer(settings.kafka_bootstrap_servers)
    await consumer.start()
    await producer.start()
    try:
        logger.info("consuming", topic=EVENTS_DEDUPED_TOPIC, spotify_enabled=spotify.enabled)
        return await consume_loop(consumer, producer, engine, mb, spotify, stop_after)
    finally:
        await consumer.stop()
        await producer.stop()
        await mb.aclose()
        await spotify.aclose()
        await engine.dispose()


async def consume_loop(
    consumer: AIOKafkaConsumer,
    producer: EnricherProducer,
    engine: AsyncEngine,
    mb: MusicBrainzClient,
    spotify: SpotifyClient,
    stop_after: int | None = None,
) -> int:
    """Process messages one at a time, committing offsets after each successful handle."""
    processed = 0
    async for message in consumer:
        try:
            await handle_message(message, producer, engine, mb, spotify)
        except ValidationError:
            # A malformed message can never succeed; skip it after logging so the
            # partition does not wedge. Anything else (DB down, MusicBrainz outage)
            # propagates and crashes the process, leaving the offset uncommitted.
            logger.exception("skipping malformed message", offset=message.offset)
        await consumer.commit()
        processed += 1
        if stop_after is not None and processed >= stop_after:
            break
    return processed


async def handle_message(
    message: ConsumerRecord,
    producer: EnricherProducer,
    engine: AsyncEngine,
    mb: MusicBrainzClient,
    spotify: SpotifyClient,
) -> None:
    """Enrich one deduped event and publish the outcome, continuing the producer's trace."""
    context = extract({name: value.decode() for name, value in message.headers})
    with tracer.start_as_current_span(
        f"consume {EVENTS_DEDUPED_TOPIC}", context=context, kind=trace.SpanKind.CONSUMER
    ):
        deduped = DedupedEvent.model_validate_json(message.value)
        result = await process_deduped(engine, mb, spotify, deduped)
        await producer.publish_enriched(
            EnrichedEvent(
                event_id=deduped.event_id,
                venue_id=deduped.venue_id,
                artist_ids=result.artist_ids,
                enriched_artist_ids=result.enriched_artist_ids,
                title=deduped.title,
                starts_at=deduped.starts_at,
                status=deduped.status,
            )
        )
        logger.info(
            "event enriched",
            event_id=str(deduped.event_id),
            artists=len(result.artist_ids),
            newly_enriched=len(result.enriched_artist_ids),
        )


if __name__ == "__main__":
    main()
