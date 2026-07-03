"""Unit tests for the Discovery API payload parser, driven by the saved fixture."""

import copy
from datetime import UTC, datetime
from typing import Any

from src.parser import ParsedEvent, parse_event, parse_page


def _event_by_id(payload: dict[str, Any], external_id: str) -> dict[str, Any]:
    """Return the raw fixture event with the given Ticketmaster id."""
    raw: dict[str, Any]
    for raw in payload["_embedded"]["events"]:
        if raw["id"] == external_id:
            return raw
    raise AssertionError(f"no fixture event with id {external_id}")


def _parsed_by_id(payload: dict[str, Any], external_id: str) -> ParsedEvent:
    """Parse the fixture event with the given Ticketmaster id."""
    event = parse_event(_event_by_id(payload, external_id))
    assert event is not None
    return event


def test_parses_all_nine_fixture_events(payload: dict[str, Any]) -> None:
    """Every fixture event is usable, so parse_page returns all nine."""
    assert len(parse_page(payload)) == 9


def test_field_mapping_for_headline_event(payload: dict[str, Any]) -> None:
    """Event fields map onto the internal model exactly as the spec dictates."""
    event = _parsed_by_id(payload, "vvG1fZ9K3sNqTm")
    assert event.title == "The National with MJ Lenderman"
    assert event.source_url is not None and event.source_url.startswith(
        "https://www.ticketmaster.com/the-national"
    )
    assert event.starts_at == datetime(2026, 10, 10, 0, 0, tzinfo=UTC)
    assert event.doors_at == datetime(2026, 10, 9, 23, 0, tzinfo=UTC)
    assert event.on_sale_at == datetime(2026, 7, 10, 14, 0, tzinfo=UTC)
    assert event.price_min_cents == 3950
    assert event.price_max_cents == 8950
    assert event.currency == "USD"
    assert event.image_url is not None and event.image_url.endswith("16_9.jpg")
    assert event.venue.name == "KEMBA Live!"
    assert event.venue.tm_id == "KovZpZAEdFtJ"
    assert event.venue.city == "Columbus"
    assert event.venue.state == "OH"
    assert event.venue.country == "US"
    assert event.venue.address == {"line1": "405 Neil Ave", "postal_code": "43215"}
    assert event.venue.longitude == -83.0118
    assert event.venue.latitude == 39.9696


def test_artists_carry_billing_order_and_genres(payload: dict[str, Any]) -> None:
    """Attractions become artists in list order with genre and subGenre names."""
    event = _parsed_by_id(payload, "vvG1fZ9K3sNqTm")
    assert [(a.name, a.billing) for a in event.artists] == [
        ("The National", 0),
        ("MJ Lenderman", 1),
    ]
    assert event.artists[0].genres == ["Rock", "Indie Rock"]
    assert event.artists[1].genres == ["Rock", "Alternative Rock"]


def test_undefined_subgenre_is_dropped(payload: dict[str, Any]) -> None:
    """A subGenre named 'Undefined' is excluded from the artist's genres."""
    event = _parsed_by_id(payload, "vvG1fZ9gLp9nCw")
    assert event.artists[0].genres == ["Dance/Electronic"]


def test_status_mapping(payload: dict[str, Any]) -> None:
    """Status codes map onto the event_status enum values."""
    assert _parsed_by_id(payload, "vvG1fZ9K3sNqTm").status == "on_sale"
    assert _parsed_by_id(payload, "vvG1fZ9kZx2wRt").status == "announced"
    assert _parsed_by_id(payload, "vvG1fZ9dNb5cXe").status == "postponed"

    raw = copy.deepcopy(_event_by_id(payload, "vvG1fZ9K3sNqTm"))
    for code, expected in [
        ("canceled", "cancelled"),
        ("cancelled", "cancelled"),
        ("rescheduled", "rescheduled"),
        ("somethingelse", "announced"),
    ]:
        raw["dates"]["status"]["code"] = code
        event = parse_event(raw)
        assert event is not None
        assert event.status == expected


def test_missing_price_ranges_yield_none(payload: dict[str, Any]) -> None:
    """Events without priceRanges get null prices and the default currency."""
    event = _parsed_by_id(payload, "vvG1fZ9kZx2wRt")
    assert event.price_min_cents is None
    assert event.price_max_cents is None
    assert event.currency == "USD"


def test_skips_event_without_start_datetime(payload: dict[str, Any]) -> None:
    """An event with no dates.start.dateTime is skipped."""
    raw = copy.deepcopy(_event_by_id(payload, "vvG1fZ9K3sNqTm"))
    del raw["dates"]["start"]["dateTime"]
    assert parse_event(raw) is None


def test_skips_event_without_venue_coordinates(payload: dict[str, Any]) -> None:
    """An event whose venue lacks coordinates, or has no venue at all, is skipped."""
    raw = copy.deepcopy(_event_by_id(payload, "vvG1fZ9K3sNqTm"))
    del raw["_embedded"]["venues"][0]["location"]
    assert parse_event(raw) is None

    raw = copy.deepcopy(_event_by_id(payload, "vvG1fZ9K3sNqTm"))
    del raw["_embedded"]["venues"]
    assert parse_event(raw) is None
