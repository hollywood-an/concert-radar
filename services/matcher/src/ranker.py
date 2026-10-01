"""Alert matching: which users should hear about which shows.

A match means an artist the user follows is on the lineup of an upcoming show inside the
user's travel radius. The score is the feed's relevance score for the headliner, carried
along for display; it does not decide whether a match happens.
"""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.schemas import MatchProposed

# An upcoming, still-sellable show in the user's radius that the user has not dismissed,
# scored on its headliner. Dismissals are excluded so alerts and the feed never disagree.
_MATCH_BASE = """
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
    WHERE e.starts_at > now()
      AND e.status IN ('announced', 'on_sale')
      AND NOT EXISTS (
          SELECT 1 FROM dismissals d WHERE d.user_id = u.id AND d.event_id = e.id
      )
"""

_MATCHES_FOR_EVENT = text(
    _MATCH_BASE
    + """
      AND e.id = :event_id
      AND EXISTS (
          SELECT 1 FROM event_artists lineup
          JOIN follows f ON f.artist_id = lineup.artist_id AND f.user_id = u.id
          WHERE lineup.event_id = e.id
      )
    """
)

# The follows join re-checks the follow, so a follow undone before this message was
# processed does not alert.
_MATCHES_FOR_FOLLOWED_ARTISTS = text(
    _MATCH_BASE
    + """
      AND u.id = :user_id
      AND EXISTS (
          SELECT 1 FROM event_artists lineup
          JOIN follows f ON f.artist_id = lineup.artist_id AND f.user_id = u.id
          WHERE lineup.event_id = e.id
            AND lineup.artist_id = ANY(CAST(:artist_ids AS uuid[]))
      )
    """
)


async def matches_for_event(engine: AsyncEngine, event_id: UUID) -> list[MatchProposed]:
    """Return every in-radius user who follows an artist on this show's lineup."""
    async with engine.connect() as conn:
        rows = (await conn.execute(_MATCHES_FOR_EVENT, {"event_id": event_id})).mappings()
        return [MatchProposed.model_validate(dict(row)) for row in rows]


async def matches_for_followed_artists(
    engine: AsyncEngine, user_id: UUID, artist_ids: list[UUID]
) -> list[MatchProposed]:
    """Return the user's upcoming in-radius shows featuring any of the just-followed artists."""
    if not artist_ids:
        return []
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                _MATCHES_FOR_FOLLOWED_ARTISTS, {"user_id": user_id, "artist_ids": artist_ids}
            )
        ).mappings()
        return [MatchProposed.model_validate(dict(row)) for row in rows]
