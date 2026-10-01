"""Pipeline test: new shows and follows produce matches on the real broker; re-scrapes do not."""

import asyncio
import json

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, ConsumerRecord
from sqlalchemy.ext.asyncio import AsyncEngine

from src.main import EVENTS_ENRICHED_TOPIC, USERS_TASTE_UPDATED_TOPIC, run
from src.producer import MATCHES_PROPOSED_TOPIC
from tests.conftest import create_event, create_user, make_enriched


async def test_new_show_and_follow_match_but_rescrape_does_not(
    kafka_bootstrap: str,
    db_engine: AsyncEngine,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A newly announced show and a follow each propose the match; a re-scrape proposes none."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", kafka_bootstrap)

    event_id, venue_id, artist_id = await create_event(db_engine, artist_name="Phoebe Bridgers")
    user_id = await create_user(db_engine, "fan@example.com", follows=("Phoebe Bridgers",))

    producer = AIOKafkaProducer(bootstrap_servers=kafka_bootstrap)
    await producer.start()
    try:
        for is_new in (True, False):
            await producer.send_and_wait(
                EVENTS_ENRICHED_TOPIC,
                make_enriched(event_id, venue_id, [artist_id], is_new=is_new)
                .model_dump_json()
                .encode(),
                key=str(event_id).encode(),
            )
        await producer.send_and_wait(
            USERS_TASTE_UPDATED_TOPIC,
            json.dumps({"user_id": str(user_id), "followed_artist_ids": [str(artist_id)]}).encode(),
            key=str(user_id).encode(),
        )
    finally:
        await producer.stop()

    processed = await run(stop_after=3)
    assert processed == 3

    consumer = AIOKafkaConsumer(
        MATCHES_PROPOSED_TOPIC,
        bootstrap_servers=kafka_bootstrap,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    messages: list[ConsumerRecord] = []
    try:
        while len(messages) < 2:
            messages.append(await asyncio.wait_for(consumer.getone(), timeout=10))
        # The re-scrape must not have proposed a third match.
        extra = await consumer.getmany(timeout_ms=3_000)
        assert not any(extra.values()), "a re-scraped show must not propose a match"
    finally:
        await consumer.stop()

    expected_key = f"{user_id}:{event_id}".encode()
    for message in messages:
        assert message.key == expected_key
        body = json.loads(message.value)
        assert body["user_id"] == str(user_id)
        assert body["event_id"] == str(event_id)
        assert body["score"] > 0.6
