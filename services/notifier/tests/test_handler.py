"""Handler tests: matches are deduped, preference-checked, and queued for the digest."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from structlog.testing import capture_logs

from src.handler import Outcome, process_match
from tests.conftest import count_rows, create_event, create_user, make_match


async def test_match_is_queued_not_emailed(db_engine: AsyncEngine) -> None:
    """A fresh match waits in pending_alerts; nothing is emailed until the digest runs."""
    user_id = await create_user(db_engine, "alertme@example.com")
    event_id = await create_event(db_engine)

    with capture_logs() as logs:
        outcome = await process_match(db_engine, make_match(user_id, event_id))

    assert outcome is Outcome.QUEUED
    assert not [entry for entry in logs if entry["event"] == "would send email"]
    async with db_engine.connect() as conn:
        row = (
            await conn.execute(text("SELECT user_id, event_id, score FROM pending_alerts"))
        ).one()
    assert (row.user_id, row.event_id) == (user_id, event_id)
    assert row.score == pytest.approx(0.72)
    assert await count_rows(db_engine, "alerts_sent") == 0


async def test_repeat_match_is_queued_once(db_engine: AsyncEngine) -> None:
    """The same match proposed twice, e.g. by a re-follow, waits in the queue once."""
    user_id = await create_user(db_engine, "once@example.com")
    event_id = await create_event(db_engine)

    first = await process_match(db_engine, make_match(user_id, event_id))
    second = await process_match(db_engine, make_match(user_id, event_id))

    assert first is Outcome.QUEUED
    assert second is Outcome.DUPLICATE
    assert await count_rows(db_engine, "pending_alerts") == 1


async def test_already_emailed_match_is_not_queued(db_engine: AsyncEngine) -> None:
    """A show the user was already emailed about never queues again."""
    user_id = await create_user(db_engine, "emailed@example.com")
    event_id = await create_event(db_engine)
    async with db_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO alerts_sent (user_id, event_id, channel) VALUES (:u, :e, 'email')"),
            {"u": user_id, "e": event_id},
        )

    outcome = await process_match(db_engine, make_match(user_id, event_id))

    assert outcome is Outcome.DUPLICATE
    assert await count_rows(db_engine, "pending_alerts") == 0


async def test_opted_out_user_is_skipped(db_engine: AsyncEngine) -> None:
    """A user with alert_email=false never has alerts queued."""
    user_id = await create_user(db_engine, "optout@example.com", alert_email=False)
    event_id = await create_event(db_engine)

    outcome = await process_match(db_engine, make_match(user_id, event_id))

    assert outcome is Outcome.OPTED_OUT
    assert await count_rows(db_engine, "pending_alerts") == 0


async def test_missing_rows_are_reported(db_engine: AsyncEngine) -> None:
    """A match referencing vanished rows resolves to MISSING without raising."""
    outcome = await process_match(db_engine, make_match(uuid4(), uuid4()))
    assert outcome is Outcome.MISSING
