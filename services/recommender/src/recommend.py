"""Discovery ranking: nearby shows by artists the user doesn't follow, diversified by genre."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

# Shows per genre before the list repeats a genre.
PER_GENRE = 2

# One candidate per headliner (their soonest show in range), so a touring artist with
# five local dates takes one slot. Candidates are ranked by cosine similarity to the
# user's taste; within each genre only the top PER_GENRE come first, and the rest
# follow them, so a small market still fills the list instead of coming back short.
_RECOMMEND_SQL = text(
    """
    WITH me AS (
        SELECT id, home_location, travel_radius_m, taste_embedding
        FROM users
        WHERE id = :user_id
          AND home_location IS NOT NULL
          AND taste_embedding IS NOT NULL
    ),
    candidates AS (
        SELECT DISTINCT ON (a.id)
            e.id AS event_id,
            e.title,
            e.starts_at,
            e.image_url,
            v.name AS venue_name,
            v.city AS venue_city,
            ST_Distance(me.home_location, v.location) AS distance_m,
            a.id AS artist_id,
            a.name AS artist_name,
            a.image_url AS artist_image_url,
            COALESCE(lower(a.genres[1]), '') AS genre,
            1 - (me.taste_embedding <=> a.embedding) AS similarity
        FROM me
        JOIN venues v ON ST_DWithin(me.home_location, v.location, me.travel_radius_m)
        JOIN events e ON e.venue_id = v.id
        JOIN event_artists ea ON ea.event_id = e.id AND ea.billing = 0
        JOIN artists a ON a.id = ea.artist_id
        WHERE e.starts_at > now()
          AND e.status IN ('announced', 'on_sale')
          AND a.embedding IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM follows f WHERE f.user_id = me.id AND f.artist_id = a.id
          )
          AND NOT EXISTS (
              SELECT 1 FROM dismissals d WHERE d.user_id = me.id AND d.event_id = e.id
          )
        ORDER BY a.id, e.starts_at
    ),
    ranked AS (
        SELECT
            *,
            row_number() OVER (
                PARTITION BY genre ORDER BY similarity DESC, artist_id
            ) AS genre_rank
        FROM candidates
    )
    SELECT
        event_id, title, starts_at, image_url, venue_name, venue_city, distance_m,
        artist_id, artist_name, artist_image_url, genre, similarity
    FROM ranked
    ORDER BY genre_rank > :per_genre, similarity DESC, artist_id
    LIMIT :limit
    """
)

_USER_EXISTS_SQL = text("SELECT EXISTS (SELECT 1 FROM users WHERE id = :user_id)")


@dataclass(frozen=True)
class Recommendation:
    """One recommended show and why it ranked where it did."""

    event_id: UUID
    title: str | None
    starts_at: datetime
    image_url: str | None
    venue_name: str
    venue_city: str | None
    distance_m: float
    artist_id: UUID
    artist_name: str
    artist_image_url: str | None
    genre: str
    similarity: float


async def recommend(engine: AsyncEngine, user_id: UUID, limit: int) -> list[Recommendation] | None:
    """Return up to `limit` recommendations, or None when the user doesn't exist.

    A user without a home location or any followed artist with an embedding has no
    taste to rank by, so gets an empty list.
    """
    async with engine.connect() as conn:
        if not (await conn.execute(_USER_EXISTS_SQL, {"user_id": user_id})).scalar_one():
            return None
        result = await conn.execute(
            _RECOMMEND_SQL, {"user_id": user_id, "limit": limit, "per_genre": PER_GENRE}
        )
        return [Recommendation(**row) for row in result.mappings()]
