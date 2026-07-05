"""alerts_sent bookkeeping: never notify a user twice about the same event on one channel."""

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

_ALREADY_SENT = text(
    "SELECT 1 FROM alerts_sent"
    " WHERE user_id = :user_id AND event_id = :event_id"
    " AND channel = cast(:channel AS alert_channel)"
)

_RECORD_SENT = text(
    "INSERT INTO alerts_sent (user_id, event_id, channel)"
    " VALUES (:user_id, :event_id, cast(:channel AS alert_channel))"
    " ON CONFLICT DO NOTHING RETURNING user_id"
)


async def already_sent(conn: AsyncConnection, user_id: UUID, event_id: UUID, channel: str) -> bool:
    """Whether this (user, event, channel) alert was already recorded."""
    row = (
        await conn.execute(
            _ALREADY_SENT, {"user_id": user_id, "event_id": event_id, "channel": channel}
        )
    ).first()
    return row is not None


async def record_sent(conn: AsyncConnection, user_id: UUID, event_id: UUID, channel: str) -> bool:
    """Record the alert; False when a concurrent duplicate got there first."""
    row = (
        await conn.execute(
            _RECORD_SENT, {"user_id": user_id, "event_id": event_id, "channel": channel}
        )
    ).first()
    return row is not None
