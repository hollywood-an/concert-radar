"""Matching queries: who should hear about an event, and what should a user hear about."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.schemas import MatchProposed

_MATCHES_FOR_EVENT = text(
    """
    SELECT
        u.id AS user_id,
        e.id AS event_id,
        relevance_score(u.taste_embedding, a.embedding, e.starts_at) AS score
    FROM events e
    JOIN venues v ON v.id = e.venue_id
    JOIN event_artists ea ON ea.event_id = e.id AND ea.billing = 0
    JOIN artists a ON a.id = ea.artist_id
    JOIN users u ON u.home_location IS NOT NULL
        AND ST_DWithin(u.home_location, v.location, u.travel_radius_m)
    WHERE e.id = :event_id
      AND e.starts_at > now()
      AND e.status IN ('announced', 'on_sale')
      AND relevance_score(u.taste_embedding, a.embedding, e.starts_at) > :threshold
    """
)

_MATCHES_FOR_USER = text(
    """
    SELECT
        u.id AS user_id,
        e.id AS event_id,
        relevance_score(u.taste_embedding, a.embedding, e.starts_at) AS score
    FROM users u
    JOIN venues v ON ST_DWithin(u.home_location, v.location, u.travel_radius_m)
    JOIN events e ON e.venue_id = v.id
    JOIN event_artists ea ON ea.event_id = e.id AND ea.billing = 0
    JOIN artists a ON a.id = ea.artist_id
    WHERE u.id = :user_id
      AND u.home_location IS NOT NULL
      AND e.starts_at > now()
      AND e.status IN ('announced', 'on_sale')
      AND relevance_score(u.taste_embedding, a.embedding, e.starts_at) > :threshold
    """
)


async def matches_for_event(
    engine: AsyncEngine, event_id: UUID, threshold: float
) -> list[MatchProposed]:
    """Return every in-radius user whose relevance score for this event beats the threshold."""
    async with engine.connect() as conn:
        rows = (
            await conn.execute(_MATCHES_FOR_EVENT, {"event_id": event_id, "threshold": threshold})
        ).mappings()
        return [MatchProposed.model_validate(dict(row)) for row in rows]


async def matches_for_user(
    engine: AsyncEngine, user_id: UUID, threshold: float
) -> list[MatchProposed]:
    """Return every upcoming in-radius event whose relevance score for this user beats it."""
    async with engine.connect() as conn:
        rows = (
            await conn.execute(_MATCHES_FOR_USER, {"user_id": user_id, "threshold": threshold})
        ).mappings()
        return [MatchProposed.model_validate(dict(row)) for row in rows]
