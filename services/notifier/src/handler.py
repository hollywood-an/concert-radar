"""Core notification logic: decide what goes into each user's next daily digest."""

from enum import StrEnum

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.channels.email import CHANNEL
from src.dedup import already_sent
from src.digest import DISRUPTED_STATUSES, queue_alert, queue_show_changes
from src.schemas import MatchProposed, StatusChange

log = structlog.get_logger()

_USER_PREFS = text("SELECT alert_email FROM users WHERE id = :id")

_EVENT_EXISTS = text("SELECT 1 FROM events WHERE id = :id")


class Outcome(StrEnum):
    """What happened to one proposed match."""

    QUEUED = "queued"
    DUPLICATE = "duplicate"
    OPTED_OUT = "opted_out"
    MISSING = "missing"


async def process_match(engine: AsyncEngine, match: MatchProposed) -> Outcome:
    """Queue the match for the user's next digest unless dedup or preferences say otherwise."""
    async with engine.begin() as conn:
        user = (await conn.execute(_USER_PREFS, {"id": match.user_id})).first()
        event = (await conn.execute(_EVENT_EXISTS, {"id": match.event_id})).first()
        if user is None or event is None:
            log.warning(
                "match references missing rows",
                user_id=str(match.user_id),
                event_id=str(match.event_id),
            )
            return Outcome.MISSING
        if await already_sent(conn, match.user_id, match.event_id, CHANNEL):
            return Outcome.DUPLICATE
        if not user.alert_email:
            return Outcome.OPTED_OUT
        if not await queue_alert(conn, match):
            return Outcome.DUPLICATE
        return Outcome.QUEUED


async def process_status_change(engine: AsyncEngine, change: StatusChange) -> int:
    """Queue change notices for users emailed about a show that fell through; return how many."""
    if change.new_status not in DISRUPTED_STATUSES:
        return 0
    async with engine.begin() as conn:
        return await queue_show_changes(conn, change.event_id)
