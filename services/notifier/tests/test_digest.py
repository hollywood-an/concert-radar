"""Digest tests: one email per user bundling every pending alert, at a fixed UTC hour."""

from collections.abc import MutableMapping
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from structlog.testing import capture_logs

from src.digest import seconds_until_next_digest, send_digests
from src.handler import process_match, process_status_change
from tests.conftest import (
    STARTS_AT,
    count_rows,
    create_event,
    create_user,
    make_match,
    make_status_change,
    mark_emailed,
    set_status,
)

EDT = timezone(timedelta(hours=-4))


def _emails(logs: list[MutableMapping[str, Any]]) -> dict[str, MutableMapping[str, Any]]:
    """Index the would-send emails in captured logs by recipient."""
    return {entry["to"]: entry for entry in logs if entry["event"] == "would send email"}


@pytest.mark.parametrize(
    ("now", "expected_hours"),
    [
        (datetime(2026, 10, 1, 9, 0, tzinfo=UTC), 5),
        (datetime(2026, 10, 1, 13, 30, tzinfo=UTC), 0.5),
        (datetime(2026, 10, 1, 14, 0, tzinfo=UTC), 24),
        (datetime(2026, 10, 1, 20, 0, tzinfo=UTC), 18),
        (datetime(2026, 10, 1, 9, 0, tzinfo=EDT), 1),
    ],
)
def test_seconds_until_next_digest(now: datetime, expected_hours: float) -> None:
    """The digest fires at the next 14:00 UTC, rolling to tomorrow once that has passed."""
    assert seconds_until_next_digest(now, 14) == expected_hours * 3600


async def test_digest_sends_one_email_per_user(db_engine: AsyncEngine) -> None:
    """Each user's pending shows go out as a single email, soonest first, and are marked sent."""
    fan = await create_user(db_engine, "digest@example.com")
    other = await create_user(db_engine, "other@example.com")
    later = await create_event(
        db_engine,
        external_id="digest-later",
        artist_name="Turnstile",
        starts_at=STARTS_AT + timedelta(days=10),
    )
    sooner = await create_event(db_engine, external_id="digest-sooner")
    for user_id, event_id in ((fan, later), (fan, sooner), (other, sooner)):
        await process_match(db_engine, make_match(user_id, event_id))

    with capture_logs() as logs:
        sent = await send_digests(db_engine)

    emails = _emails(logs)
    assert set(emails) == {"digest@example.com", "other@example.com"}
    fan_email = emails["digest@example.com"]
    assert fan_email["subject"] == "2 new shows near you"
    assert fan_email["body"].index("Phoebe Bridgers") < fan_email["body"].index("Turnstile")
    assert emails["other@example.com"]["subject"] == "1 new show near you"
    assert sorted((n.user_id, n.event_id) for n in sent) == sorted(
        [(fan, later), (fan, sooner), (other, sooner)]
    )
    assert {n.channel for n in sent} == {"email"}
    assert await count_rows(db_engine, "alerts_sent") == 3
    assert await count_rows(db_engine, "pending_alerts") == 0


async def test_alerts_gone_stale_while_waiting_are_dropped(db_engine: AsyncEngine) -> None:
    """Shows that started, were cancelled, dismissed, or left the user's range get no email."""
    cases: dict[str, tuple[UUID, UUID]] = {}
    for name, artist in (
        ("started", "Phoebe Bridgers"),
        ("cancelled", "Turnstile"),
        ("dismissed", "Khruangbin"),
        ("opted-out", "Sylvan Esso"),
        ("moved-away", "Japanese Breakfast"),
    ):
        user_id = await create_user(db_engine, f"{name}@example.com")
        event_id = await create_event(db_engine, external_id=f"stale-{name}", artist_name=artist)
        await process_match(db_engine, make_match(user_id, event_id))
        cases[name] = (user_id, event_id)
    async with db_engine.begin() as conn:
        await conn.execute(
            text("UPDATE events SET starts_at = now() - interval '1 hour' WHERE id = :e"),
            {"e": cases["started"][1]},
        )
        await conn.execute(
            text("UPDATE events SET status = 'cancelled' WHERE id = :e"),
            {"e": cases["cancelled"][1]},
        )
        await conn.execute(
            text("INSERT INTO dismissals (user_id, event_id) VALUES (:u, :e)"),
            {"u": cases["dismissed"][0], "e": cases["dismissed"][1]},
        )
        await conn.execute(
            text("UPDATE users SET alert_email = false WHERE id = :u"),
            {"u": cases["opted-out"][0]},
        )
        await conn.execute(
            text(
                "UPDATE users SET home_location ="
                " ST_SetSRID(ST_MakePoint(-122.3350, 47.6080), 4326)::geography WHERE id = :u"
            ),
            {"u": cases["moved-away"][0]},
        )

    with capture_logs() as logs:
        sent = await send_digests(db_engine)

    assert sent == []
    assert _emails(logs) == {}
    assert await count_rows(db_engine, "pending_alerts") == 0
    assert await count_rows(db_engine, "alerts_sent") == 0


async def test_digest_includes_updates_to_shows_already_sent(db_engine: AsyncEngine) -> None:
    """A cancelled show the user was emailed about goes in an updates section of the digest."""
    user_id = await create_user(db_engine, "updates@example.com")
    cancelled = await create_event(db_engine, external_id="digest-cancelled")
    upcoming = await create_event(db_engine, external_id="digest-upcoming", artist_name="Turnstile")
    await mark_emailed(db_engine, user_id, cancelled)
    await set_status(db_engine, cancelled, "cancelled")
    await process_status_change(db_engine, make_status_change(cancelled, "cancelled"))
    await process_match(db_engine, make_match(user_id, upcoming))

    with capture_logs() as logs:
        sent = await send_digests(db_engine)

    email = _emails(logs)["updates@example.com"]
    assert email["subject"] == "1 new show near you, 1 show update"
    new_shows, updates = email["body"].split("Updates to shows we told you about:")
    assert "Turnstile" in new_shows
    assert "Cancelled: Phoebe Bridgers" in updates
    assert sorted((n.kind, n.event_id) for n in sent) == sorted(
        [("new_show", upcoming), ("show_change", cancelled)]
    )
    assert await count_rows(db_engine, "pending_show_changes") == 0
    assert await count_rows(db_engine, "pending_alerts") == 0


async def test_change_notice_dropped_when_show_is_back_on(db_engine: AsyncEngine) -> None:
    """A show postponed and then back on sale before the digest sends no notice."""
    user_id = await create_user(db_engine, "relieved@example.com")
    event_id = await create_event(db_engine)
    await mark_emailed(db_engine, user_id, event_id)
    await set_status(db_engine, event_id, "postponed")
    await process_status_change(db_engine, make_status_change(event_id, "postponed"))
    await set_status(db_engine, event_id, "on_sale")

    with capture_logs() as logs:
        sent = await send_digests(db_engine)

    assert sent == []
    assert _emails(logs) == {}
    assert await count_rows(db_engine, "pending_show_changes") == 0
