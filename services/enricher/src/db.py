"""Async Postgres access for artist enrichment writes."""

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

_ARTIST_FOR_ENRICHMENT = text(
    "SELECT id, name, mbid, genres, spotify_id, embedding IS NOT NULL AS has_embedding"
    " FROM artists WHERE id = :id"
)

_ARTIST_BY_MBID = text("SELECT id FROM artists WHERE mbid = :mbid AND id != :id")

_ARTIST_ENRICH = text(
    "UPDATE artists SET"
    " mbid = coalesce(:mbid, mbid),"
    " genres = :genres,"
    " embedding = coalesce(CAST(:embedding AS vector), embedding),"
    " spotify_id = coalesce(:spotify_id, spotify_id),"
    " popularity = coalesce(:popularity, popularity),"
    " image_url = coalesce(:image_url, image_url),"
    " updated_at = now()"
    " WHERE id = :id"
)

_RELINK_EVENT_ARTISTS = text(
    "INSERT INTO event_artists (event_id, artist_id, billing)"
    " SELECT event_id, :canonical_id, billing FROM event_artists WHERE artist_id = :stub_id"
    " ON CONFLICT (event_id, artist_id) DO NOTHING"
)

_DELETE_STUB_EVENT_ARTISTS = text("DELETE FROM event_artists WHERE artist_id = :stub_id")

_RELINK_FOLLOWS = text(
    "INSERT INTO follows (user_id, artist_id, source)"
    " SELECT user_id, :canonical_id, source FROM follows WHERE artist_id = :stub_id"
    " ON CONFLICT (user_id, artist_id) DO NOTHING"
)

_DELETE_STUB_FOLLOWS = text("DELETE FROM follows WHERE artist_id = :stub_id")

_DELETE_STUB_ARTIST = text("DELETE FROM artists WHERE id = :stub_id")


async def fetch_artist(conn: AsyncConnection, artist_id: UUID) -> Any | None:
    """Return the artist row needed for enrichment decisions, or None when gone."""
    return (await conn.execute(_ARTIST_FOR_ENRICHMENT, {"id": artist_id})).first()


async def find_artist_by_mbid(conn: AsyncConnection, mbid: str, artist_id: UUID) -> UUID | None:
    """Return the id of a different artist row already holding this mbid, if any."""
    row = (await conn.execute(_ARTIST_BY_MBID, {"mbid": mbid, "id": artist_id})).first()
    return None if row is None else row[0]


async def enrich_artist(
    conn: AsyncConnection,
    artist_id: UUID,
    *,
    mbid: str | None,
    genres: list[str],
    embedding: list[float] | None,
    spotify_id: str | None = None,
    popularity: int | None = None,
    image_url: str | None = None,
) -> None:
    """Write enrichment results onto the artist row, never clearing existing values."""
    await conn.execute(
        _ARTIST_ENRICH,
        {
            "id": artist_id,
            "mbid": mbid,
            "genres": genres,
            "embedding": None if embedding is None else _vector_literal(embedding),
            "spotify_id": spotify_id,
            "popularity": popularity,
            "image_url": image_url,
        },
    )


async def merge_artist(conn: AsyncConnection, stub_id: UUID, canonical_id: UUID) -> None:
    """Re-point lineups and follows from a stub artist to the canonical row, then drop it."""
    await conn.execute(_RELINK_EVENT_ARTISTS, {"stub_id": stub_id, "canonical_id": canonical_id})
    await conn.execute(_DELETE_STUB_EVENT_ARTISTS, {"stub_id": stub_id})
    await conn.execute(_RELINK_FOLLOWS, {"stub_id": stub_id, "canonical_id": canonical_id})
    await conn.execute(_DELETE_STUB_FOLLOWS, {"stub_id": stub_id})
    await conn.execute(_DELETE_STUB_ARTIST, {"stub_id": stub_id})


def _vector_literal(embedding: list[float]) -> str:
    """Render a pgvector literal like '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{value:.6f}" for value in embedding) + "]"
