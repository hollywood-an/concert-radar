"""Ranker tests: matching outcomes follow radius, status, recency, and threshold rules."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.ranker import matches_for_event, matches_for_user
from tests.conftest import create_event, create_user


async def test_event_matches_users_in_radius(db_engine: AsyncEngine) -> None:
    """Nearby users match a new event; a distant user does not; followers score higher."""
    event_id, _, _ = await create_event(db_engine, artist_name="Phoebe Bridgers")
    follower = await create_user(db_engine, "fan@example.com", follows=("Phoebe Bridgers",))
    fresh = await create_user(db_engine, "fresh@example.com")
    await create_user(db_engine, "seattle@example.com", lon=-122.3350, lat=47.6080)

    matches = await matches_for_event(db_engine, event_id, threshold=0.3)

    by_user = {m.user_id: m for m in matches}
    assert set(by_user) == {follower, fresh}
    assert all(m.event_id == event_id for m in matches)
    assert by_user[follower].score > by_user[fresh].score
    assert by_user[fresh].score == 0.5


async def test_threshold_filters_low_scores(db_engine: AsyncEngine) -> None:
    """Raising the threshold above 0.5 drops the no-taste user but keeps the follower."""
    event_id, _, _ = await create_event(db_engine, artist_name="Phoebe Bridgers")
    follower = await create_user(db_engine, "fan@example.com", follows=("Phoebe Bridgers",))
    await create_user(db_engine, "fresh@example.com")

    matches = await matches_for_event(db_engine, event_id, threshold=0.6)
    assert [m.user_id for m in matches] == [follower]


async def test_taste_update_matches_upcoming_events_for_user(db_engine: AsyncEngine) -> None:
    """A taste update re-matches the user against upcoming in-radius events only."""
    upcoming_id, _, _ = await create_event(db_engine, artist_name="Phoebe Bridgers")
    await create_event(
        db_engine,
        artist_name="Turnstile",
        venue_name="Ace of Cups",
        starts_at=datetime.now(UTC) - timedelta(days=2),
        external_id="match-past",
    )
    await create_event(
        db_engine,
        artist_name="Khruangbin",
        venue_name="The Basement",
        status="cancelled",
        external_id="match-cancelled",
    )
    user_id = await create_user(db_engine, "fan@example.com", follows=("Phoebe Bridgers",))

    matches = await matches_for_user(db_engine, user_id, threshold=0.3)

    assert [m.event_id for m in matches] == [upcoming_id]
    assert matches[0].user_id == user_id
    assert matches[0].score > 0.6


async def test_user_without_home_location_matches_nothing(db_engine: AsyncEngine) -> None:
    """A user with no home location can never be matched."""
    event_id, _, _ = await create_event(db_engine)
    async with db_engine.begin() as conn:
        user_id = (
            await conn.execute(
                text("INSERT INTO users (email) VALUES ('nowhere@example.com') RETURNING id")
            )
        ).scalar_one()

    assert await matches_for_user(db_engine, user_id, threshold=0.3) == []
    matches = await matches_for_event(db_engine, event_id, threshold=0.3)
    assert user_id not in [m.user_id for m in matches]
