"""Follow management (Phase 3: recompute taste embedding inline, no Kafka publish yet)."""

from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import text

from src.deps import CurrentUser, DbSession
from src.models import Artist
from src.schemas import ArtistSummary, FollowRequest

router = APIRouter(tags=["follows"])
logger = structlog.get_logger()

_INSERT_FOLLOW = text(
    """
    INSERT INTO follows (user_id, artist_id, source)
    VALUES (:user_id, :artist_id, 'manual')
    ON CONFLICT (user_id, artist_id) DO NOTHING
    """
)

_DELETE_FOLLOW = text("DELETE FROM follows WHERE user_id = :user_id AND artist_id = :artist_id")

_RECOMPUTE_TASTE = text("SELECT update_user_taste_embedding(:user_id)")

_LIST_FOLLOWS = text(
    """
    SELECT
        a.id,
        a.name,
        a.image_url,
        COALESCE(a.genres, '{}') AS genres,
        TRUE AS followed
    FROM follows f
    JOIN artists a ON a.id = f.artist_id
    WHERE f.user_id = :user_id
    ORDER BY f.created_at DESC, a.name
    """
)


@router.get("/follows")
async def list_follows(user: CurrentUser, session: DbSession) -> list[ArtistSummary]:
    """Return the artists the current user follows, most recently followed first."""
    result = await session.execute(_LIST_FOLLOWS, {"user_id": user.id})
    return [ArtistSummary.model_validate(dict(row)) for row in result.mappings()]


@router.post("/follows", status_code=status.HTTP_201_CREATED)
async def create_follow(
    body: FollowRequest, user: CurrentUser, session: DbSession
) -> ArtistSummary:
    """Follow an artist and recompute the user's taste embedding. Idempotent."""
    artist = await session.get(Artist, body.artist_id)
    if artist is None:
        raise HTTPException(status_code=404, detail="artist not found")
    await session.execute(_INSERT_FOLLOW, {"user_id": user.id, "artist_id": body.artist_id})
    await session.execute(_RECOMPUTE_TASTE, {"user_id": user.id})
    await session.commit()
    logger.info("follow_created", user_id=str(user.id), artist_id=str(body.artist_id))
    return ArtistSummary(
        id=artist.id,
        name=artist.name,
        image_url=artist.image_url,
        genres=artist.genres or [],
        followed=True,
    )


@router.delete("/follows/{artist_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_follow(artist_id: UUID, user: CurrentUser, session: DbSession) -> Response:
    """Unfollow an artist and recompute the user's taste embedding. Idempotent."""
    await session.execute(_DELETE_FOLLOW, {"user_id": user.id, "artist_id": artist_id})
    await session.execute(_RECOMPUTE_TASTE, {"user_id": user.id})
    await session.commit()
    logger.info("follow_deleted", user_id=str(user.id), artist_id=str(artist_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
