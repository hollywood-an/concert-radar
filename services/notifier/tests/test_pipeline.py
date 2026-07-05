"""Pipeline test: proposed matches in, one notification out, duplicates swallowed."""

import json

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.main import MATCHES_PROPOSED_TOPIC, run
from src.producer import NOTIFICATIONS_SENT_TOPIC
from tests.conftest import create_event, create_user, make_match


async def test_match_notifies_once(
    kafka_bootstrap: str,
    db_engine: AsyncEngine,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two identical proposed matches produce exactly one notifications.sent message."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", kafka_bootstrap)

    user_id = await create_user(db_engine, "pipeline@example.com")
    event_id = await create_event(db_engine)
    match = make_match(user_id, event_id)

    producer = AIOKafkaProducer(bootstrap_servers=kafka_bootstrap)
    await producer.start()
    try:
        for _ in range(2):
            await producer.send_and_wait(
                MATCHES_PROPOSED_TOPIC,
                match.model_dump_json().encode(),
                key=f"{user_id}:{event_id}".encode(),
            )
    finally:
        await producer.stop()

    processed = await run(stop_after=2)
    assert processed == 2

    consumer = AIOKafkaConsumer(
        NOTIFICATIONS_SENT_TOPIC,
        bootstrap_servers=kafka_bootstrap,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    try:
        first = await consumer.getone()
        # The duplicate match must not have produced a second message.
        extra = await consumer.getmany(timeout_ms=3_000)
        assert not any(extra.values()), "expected exactly one notification"
    finally:
        await consumer.stop()

    assert first.key == f"{user_id}:{event_id}".encode()
    body = json.loads(first.value)
    assert body["user_id"] == str(user_id)
    assert body["event_id"] == str(event_id)
    assert body["channel"] == "email"

    async with db_engine.connect() as conn:
        count = (await conn.execute(text("SELECT count(*) FROM alerts_sent"))).scalar_one()
    assert count == 1
