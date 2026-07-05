"""Pipeline test: real broker in, enrichment writes, real broker out."""

import json

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.main import EVENTS_DEDUPED_TOPIC, run
from src.musicbrainz import MusicBrainzClient
from src.producer import EVENTS_ENRICHED_TOPIC
from src.spotify import SpotifyClient
from tests.conftest import create_artist, create_event, make_deduped, mb_artist_json, mb_transport


async def test_consume_enrich_publish_roundtrip(
    kafka_bootstrap: str,
    db_engine: AsyncEngine,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A deduped message enriches the artist in Postgres and lands on events.enriched."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", kafka_bootstrap)

    artist_id = await create_artist(db_engine, "Wet Leg")
    event_id, venue_id = await create_event(db_engine, [artist_id])
    deduped = make_deduped(event_id, venue_id, [artist_id])

    producer = AIOKafkaProducer(bootstrap_servers=kafka_bootstrap)
    await producer.start()
    try:
        await producer.send_and_wait(
            EVENTS_DEDUPED_TOPIC,
            deduped.model_dump_json().encode(),
            key=str(event_id).encode(),
        )
    finally:
        await producer.stop()

    mb = MusicBrainzClient(
        transport=mb_transport({"Wet Leg": mb_artist_json("mb-wetleg", "Wet Leg")}),
        min_interval=0.0,
    )
    processed = await run(stop_after=1, mb=mb, spotify=SpotifyClient("", ""))
    assert processed == 1

    async with db_engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT mbid, embedding IS NOT NULL AS embedded FROM artists WHERE id = :id"),
                {"id": artist_id},
            )
        ).one()
    assert row.mbid == "mb-wetleg"
    assert row.embedded is True

    consumer = AIOKafkaConsumer(
        EVENTS_ENRICHED_TOPIC,
        bootstrap_servers=kafka_bootstrap,
        auto_offset_reset="earliest",
        consumer_timeout_ms=10_000,
    )
    await consumer.start()
    try:
        message = await consumer.getone()
    finally:
        await consumer.stop()
    assert message.key == str(event_id).encode()
    body = json.loads(message.value)
    assert body["event_id"] == str(event_id)
    assert body["artist_ids"] == [str(artist_id)]
    assert body["enriched_artist_ids"] == [str(artist_id)]
