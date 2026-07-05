"""Handler tests: dedup, preference checks, and the logged email are observable."""

from datetime import time
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.handler import Outcome, in_quiet_hours, process_match
from tests.conftest import create_event, create_user, make_match


@pytest.mark.parametrize(
    ("now", "start", "end", "expected"),
    [
        (time(12, 0), None, None, False),
        (time(12, 0), time(9, 0), time(17, 0), True),
        (time(8, 59), time(9, 0), time(17, 0), False),
        (time(23, 30), time(22, 0), time(7, 0), True),
        (time(6, 59), time(22, 0), time(7, 0), True),
        (time(12, 0), time(22, 0), time(7, 0), False),
    ],
)
def test_in_quiet_hours(now: time, start: time | None, end: time | None, expected: bool) -> None:
    """Quiet windows work within a day and across midnight."""
    assert in_quiet_hours(now, start, end) is expected


async def _alert_count(engine: AsyncEngine) -> int:
    async with engine.connect() as conn:
        return int((await conn.execute(text("SELECT count(*) FROM alerts_sent"))).scalar_one())


async def test_match_sends_email_and_records_alert(
    db_engine: AsyncEngine, capsys: pytest.CaptureFixture[str]
) -> None:
    """A fresh match logs the would-send email and records it in alerts_sent."""
    user_id = await create_user(db_engine, "alertme@example.com")
    event_id = await create_event(db_engine)

    outcome = await process_match(db_engine, make_match(user_id, event_id))

    assert outcome is Outcome.SENT
    captured = capsys.readouterr().out
    assert "would send email" in captured
    assert "alertme@example.com" in captured
    assert "Phoebe Bridgers" in captured
    async with db_engine.connect() as conn:
        row = (
            await conn.execute(
                text("SELECT channel::text AS channel FROM alerts_sent WHERE user_id = :u"),
                {"u": user_id},
            )
        ).one()
    assert row.channel == "email"


async def test_second_match_is_deduplicated(db_engine: AsyncEngine) -> None:
    """The same (user, event) match never notifies twice."""
    user_id = await create_user(db_engine, "once@example.com")
    event_id = await create_event(db_engine)

    first = await process_match(db_engine, make_match(user_id, event_id))
    second = await process_match(db_engine, make_match(user_id, event_id))

    assert first is Outcome.SENT
    assert second is Outcome.DUPLICATE
    assert await _alert_count(db_engine) == 1


async def test_opted_out_user_is_skipped(db_engine: AsyncEngine) -> None:
    """A user with alert_email=false is never notified and nothing is recorded."""
    user_id = await create_user(db_engine, "optout@example.com", alert_email=False)
    event_id = await create_event(db_engine)

    outcome = await process_match(db_engine, make_match(user_id, event_id))

    assert outcome is Outcome.OPTED_OUT
    assert await _alert_count(db_engine) == 0


async def test_quiet_hours_skip_notification(db_engine: AsyncEngine) -> None:
    """A user whose quiet window covers the whole day is not notified."""
    user_id = await create_user(
        db_engine,
        "sleeping@example.com",
        quiet_hours_start=time(0, 0),
        quiet_hours_end=time(23, 59, 59),
    )
    event_id = await create_event(db_engine)

    outcome = await process_match(db_engine, make_match(user_id, event_id))

    assert outcome is Outcome.QUIET_HOURS
    assert await _alert_count(db_engine) == 0


async def test_missing_rows_are_reported(db_engine: AsyncEngine) -> None:
    """A match referencing vanished rows resolves to MISSING without raising."""
    outcome = await process_match(db_engine, make_match(uuid4(), uuid4()))
    assert outcome is Outcome.MISSING
