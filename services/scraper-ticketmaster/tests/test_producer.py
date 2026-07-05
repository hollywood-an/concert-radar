"""Producer integration tests: published messages are observable on a real broker."""

import json
from typing import Any

from aiokafka import AIOKafkaConsumer

from src.parser import parse_page
from src.producer import EVENTS_DISCOVERED_TOPIC, DiscoveredEventProducer


async def _consume_all(bootstrap: str, count: int) -> list[Any]:
    """Read `count` messages from the start of the events.discovered topic."""
    consumer = AIOKafkaConsumer(
        EVENTS_DISCOVERED_TOPIC,
        bootstrap_servers=bootstrap,
        auto_offset_reset="earliest",
        consumer_timeout_ms=10_000,
    )
    await consumer.start()
    messages = []
    try:
        async for message in consumer:
            messages.append(message)
            if len(messages) == count:
                break
    finally:
        await consumer.stop()
    return messages


async def test_publish_all_fixture_events(kafka_bootstrap: str, payload: dict[str, Any]) -> None:
    """Every parsed fixture event lands on events.discovered with key, body, and trace headers."""
    events = parse_page(payload)
    assert len(events) == 9

    producer = DiscoveredEventProducer(kafka_bootstrap)
    await producer.start()
    try:
        for event in events:
            await producer.publish(event)
    finally:
        await producer.stop()

    messages = await _consume_all(kafka_bootstrap, len(events))
    assert len(messages) == len(events)

    by_external_id = {json.loads(m.value)["external_id"]: m for m in messages}
    assert set(by_external_id) == {e.external_id for e in events}
    for event in events:
        message = by_external_id[event.external_id]
        assert message.key == f"ticketmaster:{event.external_id}".encode()
        body = json.loads(message.value)
        assert body["source"] == "ticketmaster"
        assert body["title"] == event.title
        assert body["status"] == event.status
        assert body["venue"]["tm_id"] == event.venue.tm_id
        assert [a["name"] for a in body["artists"]] == [a.name for a in event.artists]
        header_names = {name for name, _ in message.headers}
        assert "traceparent" in header_names
