"""Parse Ticketmaster Discovery API payloads into typed internal models."""

from datetime import UTC, datetime
from typing import Any

import structlog
from pydantic import BaseModel

log = structlog.get_logger()

# offsale (sales window closed or not yet open) maps to announced because event_status
# has no off-sale value; sold_out would wrongly imply no tickets remain anywhere.
_STATUS_BY_CODE = {
    "onsale": "on_sale",
    "offsale": "announced",
    "canceled": "cancelled",
    "cancelled": "cancelled",
    "postponed": "postponed",
    "rescheduled": "rescheduled",
}


class ParsedArtist(BaseModel):
    """One attraction on an event, with billing order (0 = headliner)."""

    name: str
    tm_id: str
    genres: list[str]
    billing: int


class ParsedVenue(BaseModel):
    """The venue an event takes place at."""

    tm_id: str
    name: str
    city: str | None
    state: str | None
    country: str | None
    address: dict[str, str]
    longitude: float
    latitude: float


class ParsedEvent(BaseModel):
    """A single music event scraped from the Discovery API."""

    external_id: str
    title: str
    source_url: str | None
    starts_at: datetime
    doors_at: datetime | None
    on_sale_at: datetime | None
    price_min_cents: int | None
    price_max_cents: int | None
    currency: str
    image_url: str | None
    status: str
    venue: ParsedVenue
    artists: list[ParsedArtist]


def extract_raw_events(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the raw event dicts embedded in one Discovery API page."""
    events = payload.get("_embedded", {}).get("events", [])
    return list(events)


def parse_page(payload: dict[str, Any]) -> list[ParsedEvent]:
    """Parse every usable event on one Discovery API page, skipping unusable ones."""
    parsed = []
    for raw in extract_raw_events(payload):
        event = parse_event(raw)
        if event is not None:
            parsed.append(event)
    return parsed


def parse_event(raw: dict[str, Any]) -> ParsedEvent | None:
    """Parse one raw Discovery API event, or return None when it cannot be ingested."""
    external_id = str(raw.get("id") or "")
    dates = raw.get("dates") or {}
    starts_at_raw = (dates.get("start") or {}).get("dateTime")
    if not starts_at_raw:
        log.warning("skipping event without start dateTime", external_id=external_id)
        return None
    venue = _parse_venue(raw)
    if venue is None:
        log.warning("skipping event without venue coordinates", external_id=external_id)
        return None

    price_ranges = raw.get("priceRanges") or []
    price = price_ranges[0] if price_ranges else {}
    doors_raw = dates.get("doorTime")
    on_sale_raw = ((raw.get("sales") or {}).get("public") or {}).get("startDateTime")
    status_code = str(((dates.get("status") or {}).get("code")) or "").lower()

    return ParsedEvent(
        external_id=external_id,
        title=str(raw.get("name") or ""),
        source_url=raw.get("url"),
        starts_at=_parse_datetime(starts_at_raw),
        doors_at=_parse_datetime(doors_raw) if doors_raw else None,
        on_sale_at=_parse_datetime(on_sale_raw) if on_sale_raw else None,
        price_min_cents=_to_cents(price.get("min")),
        price_max_cents=_to_cents(price.get("max")),
        currency=str(price.get("currency") or "USD"),
        image_url=_first_image_url(raw),
        status=_STATUS_BY_CODE.get(status_code, "announced"),
        venue=venue,
        artists=_parse_artists(raw),
    )


def _parse_venue(raw: dict[str, Any]) -> ParsedVenue | None:
    """Extract the first embedded venue, or None when it lacks an id or coordinates."""
    venues = (raw.get("_embedded") or {}).get("venues") or []
    if not venues:
        return None
    venue = venues[0]
    location = venue.get("location") or {}
    longitude = location.get("longitude")
    latitude = location.get("latitude")
    tm_id = str(venue.get("id") or "")
    name = venue.get("name")
    if longitude is None or latitude is None or not tm_id or not name:
        return None
    address: dict[str, str] = {}
    line1 = (venue.get("address") or {}).get("line1")
    if line1:
        address["line1"] = str(line1)
    postal_code = venue.get("postalCode")
    if postal_code:
        address["postal_code"] = str(postal_code)
    return ParsedVenue(
        tm_id=tm_id,
        name=str(name),
        city=(venue.get("city") or {}).get("name"),
        state=(venue.get("state") or {}).get("stateCode"),
        country=(venue.get("country") or {}).get("countryCode"),
        address=address,
        longitude=float(longitude),
        latitude=float(latitude),
    )


def _parse_artists(raw: dict[str, Any]) -> list[ParsedArtist]:
    """Extract embedded attractions in billing order (list order, 0 = headliner)."""
    artists: list[ParsedArtist] = []
    for attraction in (raw.get("_embedded") or {}).get("attractions") or []:
        name = attraction.get("name")
        if not name:
            continue
        artists.append(
            ParsedArtist(
                name=str(name),
                tm_id=str(attraction.get("id") or ""),
                genres=_parse_genres(attraction),
                billing=len(artists),
            )
        )
    return artists


def _parse_genres(attraction: dict[str, Any]) -> list[str]:
    """Collect genre and subGenre names from an attraction, dropping 'Undefined'."""
    genres: list[str] = []
    for classification in attraction.get("classifications") or []:
        for key in ("genre", "subGenre"):
            name = (classification.get(key) or {}).get("name")
            if name and name != "Undefined" and name not in genres:
                genres.append(str(name))
    return genres


def _first_image_url(raw: dict[str, Any]) -> str | None:
    """Return the first image URL on the event, if any."""
    for image in raw.get("images") or []:
        url = image.get("url")
        if url:
            return str(url)
    return None


def _to_cents(amount: Any) -> int | None:
    """Convert a decimal price to integer cents, or None when absent."""
    if amount is None:
        return None
    return round(float(amount) * 100)


def _parse_datetime(value: str) -> datetime:
    """Parse an ISO 8601 timestamp, normalizing to UTC."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
