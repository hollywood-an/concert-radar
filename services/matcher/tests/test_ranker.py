"""Ranker tests: a match means a followed artist plays an upcoming show in the user's radius."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.ranker import matches_for_event, matches_for_followed_artists
from tests.conftest import artist_id, create_event, create_user


async def test_new_event_matches_nearby_followers_only(db_engine: AsyncEngine) -> None:
    """Only in-radius users who follow the artist match; taste similarity alone does not."""
    event_id, _, _ = await create_event(db_engine, artist_name="Phoebe Bridgers")
    follower = await create_user(db_engine, "fan@example.com", follows=("Phoebe Bridgers",))
    await create_user(db_engine, "other@example.com", follows=("Japanese Breakfast",))
    await create_user(db_engine, "fresh@example.com")
    await create_user(
        db_engine, "seattle@example.com", lon=-122.3350, lat=47.6080, follows=("Phoebe Bridgers",)
    )

    matches = await matches_for_event(db_engine, event_id)

    assert [m.user_id for m in matches] == [follower]
    assert matches[0].event_id == event_id
    assert matches[0].score > 0.6


async def test_following_a_supporting_act_matches(db_engine: AsyncEngine) -> None:
    """A followed artist anywhere on the lineup counts, not just the headliner."""
    event_id, _, _ = await create_event(
        db_engine, artist_name="Turnstile", openers=("Phoebe Bridgers",)
    )
    follower = await create_user(db_engine, "opener-fan@example.com", follows=("Phoebe Bridgers",))

    assert [m.user_id for m in await matches_for_event(db_engine, event_id)] == [follower]


async def test_dismissed_event_is_not_matched(db_engine: AsyncEngine) -> None:
    """A show the user dismissed never alerts, from either trigger."""
    event_id, _, headliner = await create_event(db_engine, artist_name="Phoebe Bridgers")
    follower = await create_user(db_engine, "dismisser@example.com", follows=("Phoebe Bridgers",))
    async with db_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO dismissals (user_id, event_id) VALUES (:u, :e)"),
            {"u": follower, "e": event_id},
        )

    assert await matches_for_event(db_engine, event_id) == []
    assert await matches_for_followed_artists(db_engine, follower, [headliner]) == []


async def test_follow_matches_only_that_artists_upcoming_shows(db_engine: AsyncEngine) -> None:
    """A follow re-matches the just-followed artist's upcoming shows and nothing else."""
    upcoming_id, _, _ = await create_event(
        db_engine, artist_name="Phoebe Bridgers", external_id="match-pb"
    )
    await create_event(
        db_engine, artist_name="Turnstile", venue_name="Ace of Cups", external_id="match-ts"
    )
    await create_event(
        db_engine,
        artist_name="Phoebe Bridgers",
        venue_name="The Basement",
        starts_at=datetime.now(UTC) - timedelta(days=2),
        external_id="match-pb-past",
    )
    await create_event(
        db_engine,
        artist_name="Phoebe Bridgers",
        venue_name="KEMBA Live!",
        status="cancelled",
        external_id="match-pb-cancelled",
    )
    user_id = await create_user(
        db_engine, "fan@example.com", follows=("Phoebe Bridgers", "Turnstile")
    )

    matches = await matches_for_followed_artists(
        db_engine, user_id, [await artist_id(db_engine, "Phoebe Bridgers")]
    )

    assert [m.event_id for m in matches] == [upcoming_id]
    assert matches[0].user_id == user_id


async def test_unfollowed_or_empty_artist_list_matches_nothing(db_engine: AsyncEngine) -> None:
    """An unfollow (empty list) or a follow undone before processing never alerts."""
    _, _, headliner = await create_event(db_engine, artist_name="Phoebe Bridgers")
    user_id = await create_user(db_engine, "changed-mind@example.com")

    assert await matches_for_followed_artists(db_engine, user_id, []) == []
    assert await matches_for_followed_artists(db_engine, user_id, [headliner]) == []


async def test_user_without_home_location_matches_nothing(db_engine: AsyncEngine) -> None:
    """A user with no home location can never be matched, even as a follower."""
    event_id, _, headliner = await create_event(db_engine)
    async with db_engine.begin() as conn:
        user_id = (
            await conn.execute(
                text("INSERT INTO users (email) VALUES ('nowhere@example.com') RETURNING id")
            )
        ).scalar_one()
        await conn.execute(
            text("INSERT INTO follows (user_id, artist_id) VALUES (:u, :a)"),
            {"u": user_id, "a": headliner},
        )

    assert await matches_for_followed_artists(db_engine, user_id, [headliner]) == []
    assert user_id not in [m.user_id for m in await matches_for_event(db_engine, event_id)]
