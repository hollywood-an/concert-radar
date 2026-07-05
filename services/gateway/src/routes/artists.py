"""Artist search backed by the pg_trgm index on artists.name."""

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import text

from src.deps import CurrentUser, DbSession
from src.schemas import ArtistSummary

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


@router.get("/artists/search")
async def search_artists(
    user: CurrentUser,
    session: DbSession,
    q: Annotated[str, Query(min_length=1, max_length=100)],
) -> list[ArtistSummary]:
    """Return the top 10 artists matching the query by trigram similarity."""
    result = await session.execute(_SEARCH_SQL, {"user_id": user.id, "q": q})
    return [ArtistSummary.model_validate(dict(row)) for row in result.mappings()]
