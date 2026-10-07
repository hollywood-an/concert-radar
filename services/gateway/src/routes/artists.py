"""Artist search (pg_trgm on artists.name) and artist detail pages."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from src.deps import CurrentUser, DbSession
from src.schemas import ArtistDetail, ArtistSummary, UpcomingShow

router = APIRouter(tags=["artists"])

# The trigram operator alone misses short prefixes ("phoe" scores below the 0.3
# default threshold against "Phoebe Bridgers"), so ILIKE is included as a fallback.
_SEARCH_SQL = text(
    """
    SELECT
        a.id,
        a.name,
        a.image_url,
        COALESCE(a.genres, '{}') AS genres,
        EXISTS (
            SELECT 1 FROM follows f
            WHERE f.user_id = :user_id AND f.artist_id = a.id
        ) AS followed
    FROM artists a
    WHERE a.name % CAST(:q AS text)
       OR a.name ILIKE '%' || CAST(:q AS text) || '%'
    ORDER BY similarity(a.name, CAST(:q AS text)) DESC, a.name
    LIMIT 10
    """
)

_ARTIST_SQL = text(
    """
    SELECT
        a.id,
        a.name,
        a.image_url,
        COALESCE(a.genres, '{}') AS genres,
        EXISTS (
            SELECT 1 FROM follows f
            WHERE f.user_id = :user_id AND f.artist_id = a.id
        ) AS followed,
        a.embedding IS NOT NULL AS has_embedding
    FROM artists a
    WHERE a.id = :artist_id
    """
)

# Any billing counts, unlike the feed, which ranks only headliners. ST_Distance is NULL
# when the user has no home location.
_UPCOMING_SQL = text(
    """
    SELECT
        e.id AS event_id,
        e.title,
        e.starts_at,
        v.name AS venue_name,
        v.city AS venue_city,
        e.price_min_cents,
        e.price_max_cents,
        ST_Distance(u.home_location, v.location) AS distance_m,
        EXISTS (
            SELECT 1 FROM dismissals d WHERE d.user_id = u.id AND d.event_id = e.id
        ) AS dismissed
    FROM event_artists ea
    JOIN events e ON e.id = ea.event_id
    JOIN venues v ON v.id = e.venue_id
    JOIN users u ON u.id = :user_id
    WHERE ea.artist_id = :artist_id
      AND e.starts_at > now()
      AND e.status IN ('announced', 'on_sale')
    ORDER BY e.starts_at, e.id
    """
)

# The target embedding is a scalar subquery rather than a join so the planner sees a
# constant to order by, which is what lets it walk the HNSW index on artists.embedding.
_SIMILAR_SQL = text(
    """
    SELECT
        a.id,
        a.name,
        a.image_url,
        COALESCE(a.genres, '{}') AS genres,
        EXISTS (
            SELECT 1 FROM follows f
            WHERE f.user_id = :user_id AND f.artist_id = a.id
        ) AS followed
    FROM artists a
    WHERE a.id <> :artist_id
      AND a.embedding IS NOT NULL
    ORDER BY a.embedding <=> (SELECT t.embedding FROM artists t WHERE t.id = :artist_id)
    LIMIT 6
    """
)


@router.get("/artists/search")
async def search_artists(
    user: CurrentUser,
    session: DbSession,
    q: Annotated[str, Query(min_length=1, max_length=100)],
) -> list[ArtistSummary]:
    """Return the top 10 artists matching the query by trigram similarity."""
    result = await session.execute(_SEARCH_SQL, {"user_id": user.id, "q": q})
    return [ArtistSummary.model_validate(dict(row)) for row in result.mappings()]


# Declared after /artists/search so "search" is never parsed as an artist id.
@router.get("/artists/{artist_id}")
async def get_artist(artist_id: UUID, user: CurrentUser, session: DbSession) -> ArtistDetail:
    """Return an artist with its upcoming shows and the six nearest artists by embedding."""
    params = {"user_id": user.id, "artist_id": artist_id}
    artist = (await session.execute(_ARTIST_SQL, params)).mappings().one_or_none()
    if artist is None:
        raise HTTPException(status_code=404, detail="artist not found")
    upcoming = (await session.execute(_UPCOMING_SQL, params)).mappings().all()
    similar = (
        (await session.execute(_SIMILAR_SQL, params)).mappings().all()
        if artist["has_embedding"]
        else []
    )
    return ArtistDetail(
        id=artist["id"],
        name=artist["name"],
        image_url=artist["image_url"],
        genres=artist["genres"],
        followed=artist["followed"],
        upcoming=[UpcomingShow.model_validate(dict(row)) for row in upcoming],
        similar=[ArtistSummary.model_validate(dict(row)) for row in similar],
    )
