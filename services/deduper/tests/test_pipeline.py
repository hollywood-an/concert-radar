"""Pipeline test: real broker in, Postgres write, real broker out."""

import json

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from opentelemetry import trace
from opentelemetry.propagate import inject
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.main import EVENTS_DISCOVERED_TOPIC, run
from src.producer import EVENTS_DEDUPED_TOPIC, EVENTS_STATUS_CHANGED_TOPIC
from tests.conftest import make_discovered


async def _publish_discovered(bootstrap: str, payloads: list[bytes]) -> None:
    """Publish raw payloads to events.discovered with valid trace headers."""
    tracer = trace.get_tracer("test")
    producer = AIOKafkaProducer(bootstrap_servers=bootstrap)
    await producer.start()
    try:
        for payload in payloads:
            with tracer.start_as_current_span("test publish", kind=trace.SpanKind.PRODUCER):
                carrier: dict[str, str] = {}
                inject(carrier)
                headers = [(name, value.encode()) for name, value in carrier.items()]
                await producer.send_and_wait(
                    EVENTS_DISCOVERED_TOPIC, payload, key=b"test", headers=headers
                )
    finally:
        await producer.stop()


async def _consume(bootstrap: str, topic: str, count: int) -> list[dict[str, object]]:
    """Read up to `count` JSON messages from the start of a topic."""
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=bootstrap,
        auto_offset_reset="earliest",
        consumer_timeout_ms=10_000,
    )
    await consumer.start()
    bodies = []
    try:
        async for message in consumer:
            bodies.append(json.loads(message.value))
            if len(bodies) == count:
                break
    finally:
        await consumer.stop()
    return bodies


async def test_consume_write_publish_roundtrip(
    kafka_bootstrap: str,
    db_engine: AsyncEngine,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Three discovered messages become DB rows plus deduped and status-changed messages."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", kafka_bootstrap)

    on_sale = make_discovered(external_id="tm-e2e-1", title="Roundtrip Show", status="on_sale")
    cancelled = make_discovered(external_id="tm-e2e-1", title="Roundtrip Show", status="cancelled")
    malformed = b'{"source": "ticketmaster", "not_an_event": true}'
    await _publish_discovered(
        kafka_bootstrap,
        [
            on_sale.model_dump_json().encode(),
            malformed,
            cancelled.model_dump_json().encode(),
        ],
    )

    processed = await run(stop_after=3)
    assert processed == 3

    async with db_engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT id, status::text AS status FROM events"
                    " WHERE source = 'ticketmaster' AND external_id = 'tm-e2e-1'"
                )
            )
        ).one()
    assert row.status == "cancelled"

    deduped = await _consume(kafka_bootstrap, EVENTS_DEDUPED_TOPIC, 2)
    assert [d["is_new"] for d in deduped] == [True, False]
    assert {d["event_id"] for d in deduped} == {str(row.id)}

    changes = await _consume(kafka_bootstrap, EVENTS_STATUS_CHANGED_TOPIC, 1)
    assert changes[0]["old_status"] == "on_sale"
    assert changes[0]["new_status"] == "cancelled"
    assert changes[0]["event_id"] == str(row.id)
