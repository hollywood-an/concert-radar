"""Producer integration tests: published messages are observable on a real broker."""

import json
from typing import Any

from opentelemetry import trace

from src.parser import parse_page
from src.producer import DiscoveredEventProducer
from tests.conftest import consume_discovered


async def test_publish_all_fixture_events(kafka_bootstrap: str, payload: dict[str, Any]) -> None:
    """Every parsed fixture event lands on events.discovered with key, body, and trace headers."""
    events = parse_page(payload)
    assert len(events) == 9

    producer = DiscoveredEventProducer(kafka_bootstrap)
    await producer.start()
    try:
        with trace.get_tracer("test").start_as_current_span("test publish") as span:
            for event in events:
                await producer.publish(event)
    finally:
        await producer.stop()

    trace_id = format(span.get_span_context().trace_id, "032x")
    messages = await consume_discovered(kafka_bootstrap, trace_id, len(events))
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
