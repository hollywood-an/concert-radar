"""Core notification logic: dedup, preference checks, and the (logged) email send."""

from enum import StrEnum

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.channels.email import CHANNEL, send_email
from src.dedup import already_sent, record_sent
from src.schemas import MatchProposed

log = structlog.get_logger()

_USER_PREFS = text("SELECT email, alert_email FROM users WHERE id = :id")

_EVENT_DETAILS = text(
    """
    SELECT e.title, e.starts_at, e.source_url, a.name AS artist_name, v.name AS venue_name
    FROM events e
    JOIN venues v ON v.id = e.venue_id
    JOIN event_artists ea ON ea.event_id = e.id AND ea.billing = 0
    JOIN artists a ON a.id = ea.artist_id
    WHERE e.id = :id
    """
)


class Outcome(StrEnum):
    """What happened to one proposed match."""

    SENT = "sent"
    DUPLICATE = "duplicate"
    OPTED_OUT = "opted_out"
    MISSING = "missing"


async def process_match(engine: AsyncEngine, match: MatchProposed) -> Outcome:
    """Notify the user about the event unless dedup or preferences say otherwise."""
    async with engine.begin() as conn:
        user = (await conn.execute(_USER_PREFS, {"id": match.user_id})).first()
        event = (await conn.execute(_EVENT_DETAILS, {"id": match.event_id})).first()
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

        send_email(
            to=user.email,
            subject=f"New show near you: {event.artist_name} at {event.venue_name}",
            body=(
                f"{event.artist_name} — {event.title}\n"
                f"{event.venue_name}, {event.starts_at:%a %b %d %Y %I:%M %p} UTC\n"
                f"Match score: {match.score:.2f}\n"
                f"Tickets: {event.source_url or 'n/a'}"
            ),
        )
        if not await record_sent(conn, match.user_id, match.event_id, CHANNEL):
            return Outcome.DUPLICATE
        return Outcome.SENT
