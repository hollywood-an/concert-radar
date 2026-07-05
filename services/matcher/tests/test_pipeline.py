"""Pipeline test: both consumed topics produce matches on the real broker."""

import json

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from sqlalchemy.ext.asyncio import AsyncEngine

from src.main import EVENTS_ENRICHED_TOPIC, USERS_TASTE_UPDATED_TOPIC, run
from src.producer import MATCHES_PROPOSED_TOPIC
from tests.conftest import create_event, create_user, make_enriched


async def test_both_topics_produce_matches(
    kafka_bootstrap: str,
    db_engine: AsyncEngine,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An enriched event and a taste update each yield a proposed match for the same pair."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", kafka_bootstrap)

    event_id, venue_id, artist_id = await create_event(db_engine, artist_name="Phoebe Bridgers")
    user_id = await create_user(db_engine, "fan@example.com", follows=("Phoebe Bridgers",))

    producer = AIOKafkaProducer(bootstrap_servers=kafka_bootstrap)
    await producer.start()
    try:
        await producer.send_and_wait(
            EVENTS_ENRICHED_TOPIC,
            make_enriched(event_id, venue_id, [artist_id]).model_dump_json().encode(),
            key=str(event_id).encode(),
        )
        await producer.send_and_wait(
            USERS_TASTE_UPDATED_TOPIC,
            json.dumps({"user_id": str(user_id)}).encode(),
            key=str(user_id).encode(),
        )
    finally:
        await producer.stop()

    processed = await run(stop_after=2, refresh_interval=0)
    assert processed == 2

    consumer = AIOKafkaConsumer(
        MATCHES_PROPOSED_TOPIC,
        bootstrap_servers=kafka_bootstrap,
        auto_offset_reset="earliest",
        consumer_timeout_ms=10_000,
    )
    await consumer.start()
    messages = []
    try:
        async for message in consumer:
            messages.append(message)
            if len(messages) == 2:
                break
    finally:
        await consumer.stop()

    assert len(messages) == 2
    expected_key = f"{user_id}:{event_id}".encode()
    for message in messages:
        assert message.key == expected_key
        body = json.loads(message.value)
        assert body["user_id"] == str(user_id)
        assert body["event_id"] == str(event_id)
        assert body["score"] > 0.6
