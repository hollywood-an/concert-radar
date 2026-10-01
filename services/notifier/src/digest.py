"""Daily digest: matches wait in pending_alerts and go out as one email per user per day.

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

_QUEUE = text(
    "INSERT INTO pending_alerts (user_id, event_id, score)"
    " VALUES (:user_id, :event_id, :score)"
    " ON CONFLICT DO NOTHING RETURNING user_id"
)

# Alerts that stopped being worth sending while they waited: the show started, was
# cancelled or postponed, was dismissed, or is no longer in range because the user moved
# or shrank their radius, or the user turned email alerts off.
_DROP_STALE = text(
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

_USERS_WITH_PENDING = text("SELECT DISTINCT user_id FROM pending_alerts")

_USER_DIGEST = text(
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

_CLEAR_SENT = text(
    "DELETE FROM pending_alerts"
    " WHERE user_id = :user_id AND event_id = ANY(CAST(:event_ids AS uuid[]))"
)


async def queue_alert(conn: AsyncConnection, match: MatchProposed) -> bool:
    """Hold a match for the user's next digest; False when it is already waiting."""
    row = (
        await conn.execute(
            _QUEUE, {"user_id": match.user_id, "event_id": match.event_id, "score": match.score}
        )
    ).first()
    return row is not None


def seconds_until_next_digest(now: datetime, hour_utc: int) -> float:
    """Seconds from `now` until the next hour_utc:00 UTC; a full day when it is exactly then."""
    target = now.astimezone(UTC).replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _subject(count: int) -> str:
    """Digest subject line, e.g. '3 new shows near you'."""
    return f"{count} new show{'' if count == 1 else 's'} near you"


def _body(rows: Sequence[Row[Any]]) -> str:
    """Render one block per show, soonest first."""
    blocks = [
        f"{row.artist_name or row.title} — {row.title}\n"
        f"{row.venue_name}, {row.starts_at:%a %b %d %Y %I:%M %p} UTC\n"
        f"Tickets: {row.source_url or 'n/a'}"
        for row in rows
    ]
    return "Artists you follow have shows coming up near you:\n\n" + "\n\n".join(blocks)


async def _send_user_digest(engine: AsyncEngine, user_id: UUID) -> list[NotificationSent]:
    """Email one user's pending alerts as a single message and mark each one sent."""
    async with engine.begin() as conn:
        rows = (await conn.execute(_USER_DIGEST, {"user_id": user_id})).all()
        if not rows:
            return []
        send_email(to=rows[0].email, subject=_subject(len(rows)), body=_body(rows))
        event_ids = [row.event_id for row in rows]
        for event_id in event_ids:
            await record_sent(conn, user_id, event_id, CHANNEL)
        await conn.execute(_CLEAR_SENT, {"user_id": user_id, "event_ids": event_ids})
    return [
        NotificationSent(user_id=user_id, event_id=row.event_id, channel=CHANNEL, score=row.score)
        for row in rows
    ]


async def send_digests(engine: AsyncEngine) -> list[NotificationSent]:
    """Email every user with pending alerts one digest; return the alerts that went out."""
    async with engine.begin() as conn:
        await conn.execute(_DROP_STALE)
        user_ids = [row.user_id for row in await conn.execute(_USERS_WITH_PENDING)]
    sent: list[NotificationSent] = []
    for user_id in user_ids:
        sent.extend(await _send_user_digest(engine, user_id))
    log.info("digests sent", users=len(user_ids), alerts=len(sent))
    return sent


async def run_digest(engine: AsyncEngine, producer: NotifierProducer) -> None:
    """Send the digests and publish notifications.sent for every alert that went out."""
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
