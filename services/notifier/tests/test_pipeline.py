"""Pipeline test: proposed matches queue once, and the digest publishes one notification."""

import asyncio
import json

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from sqlalchemy.ext.asyncio import AsyncEngine

from src.digest import run_digest
from src.main import MATCHES_PROPOSED_TOPIC, run
from src.producer import NOTIFICATIONS_SENT_TOPIC, NotifierProducer
from tests.conftest import count_rows, create_event, create_user, make_match


async def test_duplicate_matches_queue_once_and_digest_notifies_once(
    kafka_bootstrap: str,
    db_engine: AsyncEngine,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two identical matches queue one alert; the digest sends it and publishes it once."""
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
    assert await count_rows(db_engine, "pending_alerts") == 1
    assert await count_rows(db_engine, "alerts_sent") == 0

    notifier = NotifierProducer(kafka_bootstrap)
    await notifier.start()
    try:
        await run_digest(db_engine, notifier)
    finally:
        await notifier.stop()

    consumer = AIOKafkaConsumer(
        NOTIFICATIONS_SENT_TOPIC,
        bootstrap_servers=kafka_bootstrap,
        auto_offset_reset="earliest",
    )
    await consumer.start()
    try:
        first = await asyncio.wait_for(consumer.getone(), timeout=10)
        # The duplicate match must not have produced a second notification.
        extra = await consumer.getmany(timeout_ms=3_000)
        assert not any(extra.values()), "expected exactly one notification"
    finally:
        await consumer.stop()

    assert first.key == f"{user_id}:{event_id}".encode()
    body = json.loads(first.value)
    assert body["user_id"] == str(user_id)
    assert body["event_id"] == str(event_id)
    assert body["channel"] == "email"
    assert await count_rows(db_engine, "alerts_sent") == 1
    assert await count_rows(db_engine, "pending_alerts") == 0
