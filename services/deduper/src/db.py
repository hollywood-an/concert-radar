"""Async Postgres upsert repository for discovered events (moved here from the scraper)."""

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from src.schemas import DiscoveredArtist, DiscoveredEvent, DiscoveredVenue

_VENUE_BY_SOURCE_ID = text(
    "SELECT id FROM venues WHERE source_ids ->> CAST(:source AS text) = :source_venue_id"
)

_VENUE_BY_NAME_CITY = text(
    "SELECT id FROM venues"
    " WHERE lower(name) = lower(:name)"
    " AND lower(coalesce(city, '')) = lower(coalesce(:city, ''))"
)

# Attach only when no id for this source is present yet: sources have duplicate venue
# records, and letting each duplicate overwrite the key would make source_ids churn.
_VENUE_ATTACH_SOURCE_ID = text(
    "UPDATE venues"
    " SET source_ids = coalesce(source_ids, '{}'::jsonb)"
    " || jsonb_build_object(CAST(:source AS text), CAST(:source_venue_id AS text))"
    " WHERE id = :venue_id AND source_ids ->> CAST(:source AS text) IS NULL"
)

_VENUE_INSERT = text(
    "INSERT INTO venues (name, location, address, city, state, country, source_ids)"
    " VALUES (:name, ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326)::geography,"
    " cast(:address AS jsonb), :city, :state, coalesce(:country, 'US'),"
    " jsonb_build_object(CAST(:source AS text), CAST(:source_venue_id AS text)))"
    " RETURNING id"
)

_ARTIST_BY_NAME = text("SELECT id FROM artists WHERE lower(name) = lower(:name)")

_ARTIST_INSERT = text("INSERT INTO artists (name, genres) VALUES (:name, :genres) RETURNING id")

_EVENT_STATUS = text(
    "SELECT status FROM events WHERE source = :source AND external_id = :external_id"
)

_EVENT_UPSERT = text(
    "INSERT INTO events (venue_id, title, starts_at, doors_at, on_sale_at, price_min_cents,"
    " price_max_cents, currency, status, source, external_id, source_url, image_url)"
    " VALUES (:venue_id, :title, :starts_at, :doors_at, :on_sale_at, :price_min_cents,"
    " :price_max_cents, :currency, cast(:status AS event_status), :source,"
    " :external_id, :source_url, :image_url)"
    " ON CONFLICT (source, external_id) DO UPDATE SET venue_id = EXCLUDED.venue_id,"
    " title = EXCLUDED.title, starts_at = EXCLUDED.starts_at, doors_at = EXCLUDED.doors_at,"
    " on_sale_at = EXCLUDED.on_sale_at, price_min_cents = EXCLUDED.price_min_cents,"
    " price_max_cents = EXCLUDED.price_max_cents, currency = EXCLUDED.currency,"
    " status = EXCLUDED.status, source_url = EXCLUDED.source_url,"
    " image_url = EXCLUDED.image_url, updated_at = now()"
    " RETURNING id"
)

# Fuzzy cross-source match: another source already listed a trigram-similar title at the
# same venue within 20 minutes. Those are one real-world event, not two.
_CROSS_SOURCE_DUPLICATE = text(
    "SELECT id FROM events"
    " WHERE venue_id = :venue_id"
    " AND source != :source"
    " AND starts_at BETWEEN CAST(:starts_at AS timestamptz) - interval '20 minutes'"
    " AND CAST(:starts_at AS timestamptz) + interval '20 minutes'"
    " AND similarity(title, :title) > 0.6"
    " ORDER BY similarity(title, :title) DESC"
    " LIMIT 1"
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


async def upsert_venue(
    conn: AsyncConnection, source: str, venue: DiscoveredVenue
) -> tuple[UUID, bool]:
    """Match a venue by source id, then by (name, city), else insert; return (id, created)."""
    params = {"source": source, "source_venue_id": venue.tm_id}
    row = (await conn.execute(_VENUE_BY_SOURCE_ID, params)).first()
    if row is not None:
        venue_id: UUID = row[0]
        return venue_id, False

    row = (
        await conn.execute(_VENUE_BY_NAME_CITY, {"name": venue.name, "city": venue.city})
    ).first()
    if row is not None:
        matched_id: UUID = row[0]
        await conn.execute(_VENUE_ATTACH_SOURCE_ID, {**params, "venue_id": matched_id})
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
                **params,
            },
        )
    ).one()
    inserted_id: UUID = inserted[0]
    return inserted_id, True


async def upsert_artist(conn: AsyncConnection, artist: DiscoveredArtist) -> tuple[UUID, bool]:
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


async def fetch_event_status(conn: AsyncConnection, source: str, external_id: str) -> str | None:
    """Return the stored status for a source event, or None when it is new."""
    row = (
        await conn.execute(_EVENT_STATUS, {"source": source, "external_id": external_id})
    ).first()
    return None if row is None else str(row[0])


async def find_cross_source_duplicate(
    conn: AsyncConnection, event: DiscoveredEvent, venue_id: UUID
) -> UUID | None:
    """Return an existing event from another source that fuzzy-matches this discovery."""
    row = (
        await conn.execute(
            _CROSS_SOURCE_DUPLICATE,
            {
                "venue_id": venue_id,
                "source": event.source,
                "starts_at": event.starts_at,
                "title": event.title,
            },
        )
    ).first()
    return None if row is None else row[0]


async def upsert_event(conn: AsyncConnection, event: DiscoveredEvent, venue_id: UUID) -> UUID:
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
                "source": event.source,
                "external_id": event.external_id,
                "source_url": event.source_url,
                "image_url": event.image_url,
            },
        )
    ).one()
    event_id: UUID = row[0]
    return event_id


async def link_lineup(
    conn: AsyncConnection,
    event_id: UUID,
    artists: list[DiscoveredArtist],
    *,
    prune: bool,
) -> tuple[list[UUID], int]:
    """Upsert lineup links for an event; return (artist ids, artists created)."""
    created = 0
    linked: list[UUID] = []
    for artist in artists:
        artist_id, artist_created = await upsert_artist(conn, artist)
        if artist_created:
            created += 1
        await conn.execute(
            _EVENT_ARTIST_UPSERT,
            {"event_id": event_id, "artist_id": artist_id, "billing": artist.billing},
        )
        linked.append(artist_id)
    # An empty attractions list is treated as missing source data, not a cleared lineup,
    # so pruning only runs when the fresh lineup is non-empty.
    if prune and linked:
        await conn.execute(_EVENT_ARTIST_PRUNE, {"event_id": event_id, "artist_ids": linked})
    return linked, created
