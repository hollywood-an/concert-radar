"""Ranked upcoming-events feed with optional filters (direct SQL, no materialized view)."""

import base64
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from src.deps import CurrentUser, DbSession
from src.experiments import FEED_RANKING
from src.schemas import FeedItem, FeedPage

router = APIRouter(tags=["feed"])

# The visible-feed-item base is shared with the WebSocket push (src/ws.py), which
# appends an event filter instead of the filter/order/limit tail below.
FEED_ITEM_BASE = """
    SELECT
        e.id AS event_id,
        e.title,
        e.starts_at,
        e.status::text AS status,
        e.price_min_cents,
        e.price_max_cents,
        e.source_url,
        e.image_url,
        v.name AS venue_name,
        v.city AS venue_city,
        ST_Y(v.location::geometry) AS venue_lat,
        ST_X(v.location::geometry) AS venue_lon,
        ST_Distance(u.home_location, v.location) AS distance_m,
        a.id AS artist_id,
        a.name AS artist_name,
        a.image_url AS artist_image_url,
        COALESCE(a.genres, '{}') AS artist_genres,
        relevance_score(u.taste_embedding, a.embedding, e.starts_at) AS score
    FROM users u
    JOIN venues v ON ST_DWithin(u.home_location, v.location, u.travel_radius_m)
    JOIN events e ON e.venue_id = v.id
    JOIN event_artists ea ON ea.event_id = e.id AND ea.billing = 0
    JOIN artists a ON a.id = ea.artist_id
    WHERE u.id = :user_id
      AND e.starts_at > now()
      AND e.status IN ('announced', 'on_sale')
      AND NOT EXISTS (
          SELECT 1 FROM dismissals d WHERE d.user_id = u.id AND d.event_id = e.id
      )
"""

# Filter params are always bound; a NULL value disables that filter. Genres are
# lowercased on both sides so 'Rock' from Ticketmaster matches a 'rock' checkbox.
_FEED_SQL = text(
    FEED_ITEM_BASE
    + """
      AND (CAST(:date_from AS timestamptz) IS NULL OR e.starts_at >= :date_from)
      AND (CAST(:date_to AS timestamptz) IS NULL OR e.starts_at <= :date_to)
      AND (CAST(:max_distance_m AS float) IS NULL
           OR ST_Distance(u.home_location, v.location) <= :max_distance_m)
      AND (CAST(:max_price_cents AS int) IS NULL
           OR e.price_min_cents <= :max_price_cents)
      AND (CAST(:genres AS text[]) IS NULL OR EXISTS (
          SELECT 1 FROM unnest(COALESCE(a.genres, '{}')) AS g
          WHERE lower(g) = ANY(CAST(:genres AS text[]))
      ))
    ORDER BY
        CASE WHEN CAST(:followed_first AS boolean) AND EXISTS (
            SELECT 1 FROM follows f WHERE f.user_id = u.id AND f.artist_id = a.id
        ) THEN 0 ELSE 1 END,
        score DESC, e.starts_at, e.id
    LIMIT :limit OFFSET :offset
    """
)

# The two orderings can only differ for a user who follows somebody, so only those users
# enter the experiment. Counting the rest would add users whose feed was the same either
# way and blur any difference.
_RECORD_EXPOSURE = text(
    """
    INSERT INTO experiment_exposures (experiment, user_id, variant)
    SELECT CAST(:experiment AS text), CAST(:user_id AS uuid), CAST(:variant AS text)
    WHERE EXISTS (SELECT 1 FROM follows WHERE user_id = CAST(:user_id AS uuid))
    ON CONFLICT (experiment, user_id) DO NOTHING
    """
)


def _decode_cursor(cursor: str | None) -> int:
    """Decode the opaque pagination cursor into a non-negative row offset."""
    if cursor is None:
        return 0
    try:
        offset = int(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("ascii"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid cursor") from exc
    if offset < 0:
        raise HTTPException(status_code=400, detail="invalid cursor")
    return offset


def _encode_cursor(offset: int) -> str:
    """Encode a row offset as an opaque cursor."""
    return base64.urlsafe_b64encode(str(offset).encode("ascii")).decode("ascii")


@router.get("/feed")
async def get_feed(
    user: CurrentUser,
    session: DbSession,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    max_distance_m: Annotated[float | None, Query(gt=0)] = None,
    max_price_cents: Annotated[int | None, Query(gt=0)] = None,
    genres: Annotated[list[str] | None, Query()] = None,
) -> FeedPage:
    """Return the user's upcoming events ranked by relevance score, paginated by cursor.

    Equal scores sort soonest first. A user who follows nobody has no taste vector, so
    every show scores the same and the feed reads as a plain calendar.

    The order is under an A/B test (`FEED_RANKING`): half of users get shows by artists
    they follow listed first. The first page records which variant the user saw.

    Optional filters narrow the result: a date window, a maximum venue distance, a
    maximum minimum-ticket price (events without price data are excluded when set),
    and a genre list matched case-insensitively against the headliner's genres.
    """
    offset = _decode_cursor(cursor)
    variant = FEED_RANKING.variant_for(user.id)
    result = await session.execute(
        _FEED_SQL,
        {
            "user_id": user.id,
            "limit": limit + 1,
            "offset": offset,
            "date_from": date_from,
            "date_to": date_to,
            "max_distance_m": max_distance_m,
            "max_price_cents": max_price_cents,
            "genres": [g.lower() for g in genres] if genres else None,
            "followed_first": variant == FEED_RANKING.treatment,
        },
    )
    rows = result.mappings().all()
    if offset == 0:
        await session.execute(
            _RECORD_EXPOSURE,
            {"experiment": FEED_RANKING.key, "user_id": user.id, "variant": variant},
        )
        await session.commit()
    has_more = len(rows) > limit
    return FeedPage(
        items=[FeedItem.model_validate(dict(row)) for row in rows[:limit]],
        next_cursor=_encode_cursor(offset + limit) if has_more else None,
        has_more=has_more,
    )
