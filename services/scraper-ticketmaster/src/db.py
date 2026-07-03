"""Async Postgres upsert repository for scraped Ticketmaster events (Phase 2: no Kafka)."""

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from src.parser import ParsedArtist, ParsedEvent, ParsedVenue, extract_raw_events, parse_page

log = structlog.get_logger()

_VENUE_BY_TM_ID = text("SELECT id FROM venues WHERE source_ids->>'ticketmaster' = :tm_id")

_VENUE_BY_NAME_CITY = text(
    "SELECT id FROM venues"
    " WHERE lower(name) = lower(:name)"
    " AND lower(coalesce(city, '')) = lower(coalesce(:city, ''))"
)

# Attach only when no TM id is present yet: Ticketmaster has duplicate venue records,
# and letting each duplicate overwrite the key would make source_ids churn between runs.
_VENUE_ATTACH_TM_ID = text(
    "UPDATE venues"
    " SET source_ids = coalesce(source_ids, '{}'::jsonb)"
    " || jsonb_build_object('ticketmaster', cast(:tm_id AS text))"
    " WHERE id = :venue_id AND source_ids->>'ticketmaster' IS NULL"
)

_VENUE_INSERT = text(
    "INSERT INTO venues (name, location, address, city, state, country, source_ids)"
    " VALUES (:name, ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326)::geography,"
    " cast(:address AS jsonb), :city, :state, coalesce(:country, 'US'),"
    " jsonb_build_object('ticketmaster', cast(:tm_id AS text)))"
    " RETURNING id"
)

_ARTIST_BY_NAME = text("SELECT id FROM artists WHERE lower(name) = lower(:name)")

_ARTIST_INSERT = text("INSERT INTO artists (name, genres) VALUES (:name, :genres) RETURNING id")

_EVENT_STATUS = text(
    "SELECT status FROM events WHERE source = 'ticketmaster' AND external_id = :external_id"
)

_EVENT_UPSERT = text(
    "INSERT INTO events (venue_id, title, starts_at, doors_at, on_sale_at, price_min_cents,"
    " price_max_cents, currency, status, source, external_id, source_url, image_url)"
    " VALUES (:venue_id, :title, :starts_at, :doors_at, :on_sale_at, :price_min_cents,"
    " :price_max_cents, :currency, cast(:status AS event_status), 'ticketmaster',"
    " :external_id, :source_url, :image_url)"
    " ON CONFLICT (source, external_id) DO UPDATE SET venue_id = EXCLUDED.venue_id,"
    " title = EXCLUDED.title, starts_at = EXCLUDED.starts_at, doors_at = EXCLUDED.doors_at,"
    " on_sale_at = EXCLUDED.on_sale_at, price_min_cents = EXCLUDED.price_min_cents,"
    " price_max_cents = EXCLUDED.price_max_cents, currency = EXCLUDED.currency,"
    " status = EXCLUDED.status, source_url = EXCLUDED.source_url,"
    " image_url = EXCLUDED.image_url, updated_at = now()"
    " RETURNING id"
)

_EVENT_ARTIST_UPSERT = text(
    "INSERT INTO event_artists (event_id, artist_id, billing)"
    " VALUES (:event_id, :artist_id, :billing)"
    " ON CONFLICT (event_id, artist_id) DO UPDATE SET billing = EXCLUDED.billing"
)

_EVENT_ARTIST_PRUNE = text(
    "DELETE FROM event_artists"
    " WHERE event_id = :event_id AND artist_id != ALL(cast(:artist_ids AS uuid[]))"
)


@dataclass
class IngestStats:
    """Counters describing the outcome of one scrape run."""

    events_seen: int = 0
    events_new: int = 0
    events_updated: int = 0
    status_changes: int = 0
    venues_created: int = 0
    artists_created: int = 0


async def ingest_payload(
    engine: AsyncEngine, payload: dict[str, Any], stats: IngestStats | None = None
) -> IngestStats:
    """Parse one Discovery API page and upsert its events, one transaction per event."""
    stats = stats if stats is not None else IngestStats()
    stats.events_seen += len(extract_raw_events(payload))
    for event in parse_page(payload):
        async with engine.begin() as conn:
            await _ingest_event(conn, event, stats)
    return stats


async def _ingest_event(conn: AsyncConnection, event: ParsedEvent, stats: IngestStats) -> None:
    """Upsert one event with its venue, artists, and lineup links."""
    venue_id, venue_created = await _upsert_venue(conn, event.venue)
    if venue_created:
        stats.venues_created += 1

    previous_status = await _fetch_event_status(conn, event.external_id)
    event_id = await _upsert_event(conn, event, venue_id)
    if previous_status is None:
        stats.events_new += 1
    else:
        stats.events_updated += 1
        # on_sale -> announced is the offsale mapping closing a sales window (the enum has
        # no off-sale value), not a real status regression, so it is not worth alerting on.
        if previous_status != event.status and not (
            previous_status == "on_sale" and event.status == "announced"
        ):
            stats.status_changes += 1
            log.info(
                "event status changed",
                external_id=event.external_id,
                event_id=str(event_id),
                old_status=previous_status,
                new_status=event.status,
            )

    linked_artist_ids: list[UUID] = []
    for artist in event.artists:
        artist_id, artist_created = await _upsert_artist(conn, artist)
        if artist_created:
            stats.artists_created += 1
        await conn.execute(
            _EVENT_ARTIST_UPSERT,
            {"event_id": event_id, "artist_id": artist_id, "billing": artist.billing},
        )
        linked_artist_ids.append(artist_id)
    # An empty attractions list is treated as missing source data, not a cleared lineup,
    # so pruning only runs when the fresh lineup is non-empty.
    if linked_artist_ids:
        await conn.execute(
            _EVENT_ARTIST_PRUNE,
            {"event_id": event_id, "artist_ids": linked_artist_ids},
        )


async def _upsert_venue(conn: AsyncConnection, venue: ParsedVenue) -> tuple[UUID, bool]:
    """Match a venue by Ticketmaster id, then by (name, city), else insert; return (id, created)."""
    row = (await conn.execute(_VENUE_BY_TM_ID, {"tm_id": venue.tm_id})).first()
    if row is not None:
        venue_id: UUID = row[0]
        return venue_id, False

    row = (
        await conn.execute(_VENUE_BY_NAME_CITY, {"name": venue.name, "city": venue.city})
    ).first()
    if row is not None:
        matched_id: UUID = row[0]
        await conn.execute(_VENUE_ATTACH_TM_ID, {"tm_id": venue.tm_id, "venue_id": matched_id})
        return matched_id, False

    inserted = (
        await conn.execute(
            _VENUE_INSERT,
            {
                "name": venue.name,
                "longitude": venue.longitude,
                "latitude": venue.latitude,
                "address": json.dumps(venue.address),
                "city": venue.city,
                "state": venue.state,
                "country": venue.country,
                "tm_id": venue.tm_id,
            },
        )
    ).one()
    inserted_id: UUID = inserted[0]
    return inserted_id, True


async def _upsert_artist(conn: AsyncConnection, artist: ParsedArtist) -> tuple[UUID, bool]:
    """Reuse an artist by case-insensitive name, else insert bare; return (id, created)."""
    row = (await conn.execute(_ARTIST_BY_NAME, {"name": artist.name})).first()
    if row is not None:
        artist_id: UUID = row[0]
        return artist_id, False
    inserted = (
        await conn.execute(_ARTIST_INSERT, {"name": artist.name, "genres": artist.genres})
    ).one()
    inserted_id: UUID = inserted[0]
    return inserted_id, True


async def _fetch_event_status(conn: AsyncConnection, external_id: str) -> str | None:
    """Return the stored status for a Ticketmaster event, or None when it is new."""
    row = (await conn.execute(_EVENT_STATUS, {"external_id": external_id})).first()
    return None if row is None else str(row[0])


async def _upsert_event(conn: AsyncConnection, event: ParsedEvent, venue_id: UUID) -> UUID:
    """Insert or update the event row and return its id."""
    row = (
        await conn.execute(
            _EVENT_UPSERT,
            {
                "venue_id": venue_id,
                "title": event.title,
                "starts_at": event.starts_at,
                "doors_at": event.doors_at,
                "on_sale_at": event.on_sale_at,
                "price_min_cents": event.price_min_cents,
                "price_max_cents": event.price_max_cents,
                "currency": event.currency,
                "status": event.status,
                "external_id": event.external_id,
                "source_url": event.source_url,
                "image_url": event.image_url,
            },
        )
    ).one()
    event_id: UUID = row[0]
    return event_id
