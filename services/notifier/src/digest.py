"""Daily digest: one email per user per day with new shows and changes to shows already sent.

New-show alerts wait in pending_alerts; notices about shows the user was already emailed
about that were then cancelled, postponed, or rescheduled wait in pending_show_changes.
Every user gets the digest at the same fixed UTC hour because users have no timezone;
the default 14:00 UTC is 10am US Eastern during daylight saving time.
"""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import Row, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from src.channels.email import CHANNEL, send_email
from src.dedup import record_sent
from src.producer import NotifierProducer
from src.schemas import MatchProposed, NotificationSent

log = structlog.get_logger()

# Statuses that break the plans of someone who was told about the show.
DISRUPTED_STATUSES = frozenset({"cancelled", "postponed", "rescheduled"})

_QUEUE_NEW_SHOW = text(
    "INSERT INTO pending_alerts (user_id, event_id, score)"
    " VALUES (:user_id, :event_id, :score)"
    " ON CONFLICT DO NOTHING RETURNING user_id"
)

_QUEUE_SHOW_CHANGE = text(
    """
    INSERT INTO pending_show_changes (user_id, event_id)
    SELECT user_id, event_id FROM alerts_sent
    WHERE event_id = :event_id AND channel = CAST(:channel AS alert_channel)
    ON CONFLICT DO NOTHING
    RETURNING user_id
    """
)

# New-show alerts that stopped being worth sending while they waited: the show started,
# was cancelled or postponed, was dismissed, or is no longer in range because the user
# moved or shrank their radius, or the user turned email alerts off.
_DROP_STALE_NEW_SHOWS = text(
    """
    DELETE FROM pending_alerts p
    USING events e, venues v, users u
    WHERE e.id = p.event_id
      AND v.id = e.venue_id
      AND u.id = p.user_id
      AND (
          e.starts_at <= now()
          OR e.status NOT IN ('announced', 'on_sale')
          OR NOT u.alert_email
          OR u.home_location IS NULL
          OR NOT ST_DWithin(u.home_location, v.location, u.travel_radius_m)
          OR EXISTS (
              SELECT 1 FROM dismissals d WHERE d.user_id = p.user_id AND d.event_id = p.event_id
          )
      )
    """
)

# Change notices that no longer apply: the show is back on sale or its date has passed,
# the user dismissed it, or the user turned email alerts off.
_DROP_STALE_CHANGES = text(
    """
    DELETE FROM pending_show_changes p
    USING events e, users u
    WHERE e.id = p.event_id
      AND u.id = p.user_id
      AND (
          e.starts_at <= now()
          OR NOT (CAST(e.status AS text) = ANY(CAST(:disrupted AS text[])))
          OR NOT u.alert_email
          OR EXISTS (
              SELECT 1 FROM dismissals d WHERE d.user_id = p.user_id AND d.event_id = p.event_id
          )
      )
    """
)

_USERS_WITH_PENDING = text(
    "SELECT user_id FROM pending_alerts UNION SELECT user_id FROM pending_show_changes"
)

_USER_NEW_SHOWS = text(
    """
    SELECT u.email, p.event_id, p.score, e.title, e.starts_at, e.source_url,
           v.name AS venue_name, a.name AS artist_name
    FROM pending_alerts p
    JOIN users u ON u.id = p.user_id
    JOIN events e ON e.id = p.event_id
    JOIN venues v ON v.id = e.venue_id
    LEFT JOIN event_artists ea ON ea.event_id = e.id AND ea.billing = 0
    LEFT JOIN artists a ON a.id = ea.artist_id
    WHERE p.user_id = :user_id
    ORDER BY e.starts_at, e.id
    """
)

_USER_CHANGES = text(
    """
    SELECT u.email, p.event_id, CAST(e.status AS text) AS status, e.title, e.starts_at,
           v.name AS venue_name, a.name AS artist_name
    FROM pending_show_changes p
    JOIN users u ON u.id = p.user_id
    JOIN events e ON e.id = p.event_id
    JOIN venues v ON v.id = e.venue_id
    LEFT JOIN event_artists ea ON ea.event_id = e.id AND ea.billing = 0
    LEFT JOIN artists a ON a.id = ea.artist_id
    WHERE p.user_id = :user_id
    ORDER BY e.starts_at, e.id
    """
)

_CLEAR_NEW_SHOWS = text(
    "DELETE FROM pending_alerts"
    " WHERE user_id = :user_id AND event_id = ANY(CAST(:event_ids AS uuid[]))"
)

_CLEAR_CHANGES = text(
    "DELETE FROM pending_show_changes"
    " WHERE user_id = :user_id AND event_id = ANY(CAST(:event_ids AS uuid[]))"
)


async def queue_alert(conn: AsyncConnection, match: MatchProposed) -> bool:
    """Hold a match for the user's next digest; False when it is already waiting."""
    row = (
        await conn.execute(
            _QUEUE_NEW_SHOW,
            {"user_id": match.user_id, "event_id": match.event_id, "score": match.score},
        )
    ).first()
    return row is not None


async def queue_show_changes(conn: AsyncConnection, event_id: UUID) -> int:
    """Queue a change notice for every user already emailed about the show; return how many."""
    rows = (
        await conn.execute(_QUEUE_SHOW_CHANGE, {"event_id": event_id, "channel": CHANNEL})
    ).all()
    return len(rows)


def seconds_until_next_digest(now: datetime, hour_utc: int) -> float:
    """Seconds from `now` until the next hour_utc:00 UTC; a full day when it is exactly then."""
    target = now.astimezone(UTC).replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _subject(new_count: int, change_count: int) -> str:
    """Digest subject line, e.g. '2 new shows near you, 1 show update'."""
    parts: list[str] = []
    if new_count:
        parts.append(f"{new_count} new show{'' if new_count == 1 else 's'} near you")
    if change_count:
        parts.append(f"{change_count} show update{'' if change_count == 1 else 's'}")
    return ", ".join(parts)


def _describe(row: Row[Any]) -> str:
    """Two-line description of a show: who and what, then where and when."""
    return (
        f"{row.artist_name or row.title} — {row.title}\n"
        f"{row.venue_name}, {row.starts_at:%a %b %d %Y %I:%M %p} UTC"
    )


def _body(new_shows: Sequence[Row[Any]], changes: Sequence[Row[Any]]) -> str:
    """Render new shows, then changes to shows already sent, each soonest first."""
    sections: list[str] = []
    if new_shows:
        blocks = [f"{_describe(row)}\nTickets: {row.source_url or 'n/a'}" for row in new_shows]
        sections.append(
            "Artists you follow have shows coming up near you:\n\n" + "\n\n".join(blocks)
        )
    if changes:
        blocks = [f"{row.status.capitalize()}: {_describe(row)}" for row in changes]
        sections.append("Updates to shows we told you about:\n\n" + "\n\n".join(blocks))
    return "\n\n\n".join(sections)


async def _send_user_digest(engine: AsyncEngine, user_id: UUID) -> list[NotificationSent]:
    """Email one user a single message covering everything pending, and mark it all sent."""
    async with engine.begin() as conn:
        new_shows = (await conn.execute(_USER_NEW_SHOWS, {"user_id": user_id})).all()
        changes = (await conn.execute(_USER_CHANGES, {"user_id": user_id})).all()
        if not new_shows and not changes:
            return []
        send_email(
            to=(new_shows or changes)[0].email,
            subject=_subject(len(new_shows), len(changes)),
            body=_body(new_shows, changes),
        )
        for row in new_shows:
            await record_sent(conn, user_id, row.event_id, CHANNEL)
        await conn.execute(
            _CLEAR_NEW_SHOWS, {"user_id": user_id, "event_ids": [r.event_id for r in new_shows]}
        )
        await conn.execute(
            _CLEAR_CHANGES, {"user_id": user_id, "event_ids": [r.event_id for r in changes]}
        )
    return [
        NotificationSent(
            user_id=user_id,
            event_id=row.event_id,
            channel=CHANNEL,
            kind="new_show",
            score=row.score,
        )
        for row in new_shows
    ] + [
        NotificationSent(
            user_id=user_id, event_id=row.event_id, channel=CHANNEL, kind="show_change", score=None
        )
        for row in changes
    ]


async def send_digests(engine: AsyncEngine) -> list[NotificationSent]:
    """Email every user with anything pending one digest; return what went out."""
    async with engine.begin() as conn:
        await conn.execute(_DROP_STALE_NEW_SHOWS)
        await conn.execute(_DROP_STALE_CHANGES, {"disrupted": sorted(DISRUPTED_STATUSES)})
        user_ids = [row.user_id for row in await conn.execute(_USERS_WITH_PENDING)]
    sent: list[NotificationSent] = []
    for user_id in user_ids:
        sent.extend(await _send_user_digest(engine, user_id))
    log.info(
        "digests sent",
        users=len(user_ids),
        new_shows=sum(n.kind == "new_show" for n in sent),
        show_changes=sum(n.kind == "show_change" for n in sent),
    )
    return sent


async def run_digest(engine: AsyncEngine, producer: NotifierProducer) -> None:
    """Send the digests and publish notifications.sent for everything that went out."""
    for notification in await send_digests(engine):
        await producer.publish_sent(notification)


async def daily_digests(engine: AsyncEngine, producer: NotifierProducer, hour_utc: int) -> None:
    """Run the digest every day at hour_utc:00 UTC until cancelled."""
    while True:
        await asyncio.sleep(seconds_until_next_digest(datetime.now(UTC), hour_utc))
        try:
            await run_digest(engine, producer)
        except Exception:
            log.exception("digest run failed")
