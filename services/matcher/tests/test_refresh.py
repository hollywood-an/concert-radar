"""Refresh tests: the materialized view reflects new rows after a concurrent refresh."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.refresh import refresh_feed_view
from tests.conftest import create_event, create_user


async def test_refresh_materializes_new_rows(db_engine: AsyncEngine) -> None:
    """A new user and event appear in upcoming_user_feed only after a refresh."""
    event_id, _, _ = await create_event(db_engine, artist_name="Phoebe Bridgers")
    user_id = await create_user(db_engine, "viewer@example.com", follows=("Phoebe Bridgers",))

    await refresh_feed_view(db_engine)

    async with db_engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT event_id, artist_name, score FROM upcoming_user_feed"
                    " WHERE user_id = :user_id"
                ),
                {"user_id": user_id},
            )
        ).one()
    assert row.event_id == event_id
    assert row.artist_name == "Phoebe Bridgers"
    assert row.score > 0.5
