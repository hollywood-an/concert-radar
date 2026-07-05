"""Core dedup logic: resolve one discovered event to a canonical database row."""

from dataclasses import dataclass, field
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine

from src.db import (
    fetch_event_status,
    find_cross_source_duplicate,
    link_lineup,
    upsert_event,
    upsert_venue,
)
from src.schemas import DiscoveredEvent

log = structlog.get_logger()


@dataclass
class DedupResult:
    """Outcome of processing one events.discovered message."""

    event_id: UUID
    venue_id: UUID
    artist_ids: list[UUID] = field(default_factory=list)
    is_new: bool = False
    merged_cross_source: bool = False
    old_status: str | None = None


async def process_discovered(engine: AsyncEngine, event: DiscoveredEvent) -> DedupResult:
    """Upsert one discovered event with its venue, artists, and lineup links."""
    async with engine.begin() as conn:
        venue_id, venue_created = await upsert_venue(conn, event.source, event.venue)
        if venue_created:
            log.info("venue created", venue=event.venue.name, source=event.source)

        previous_status = await fetch_event_status(conn, event.source, event.external_id)
        if previous_status is None:
            duplicate_id = await find_cross_source_duplicate(conn, event, venue_id)
            if duplicate_id is not None:
                # Another source already listed this event: link this source's lineup to the
                # existing row but do not overwrite its fields (first source wins) or prune
                # a possibly richer lineup.
                artist_ids, _ = await link_lineup(conn, duplicate_id, event.artists, prune=False)
                log.info(
                    "cross-source duplicate merged",
                    event_id=str(duplicate_id),
                    source=event.source,
                    external_id=event.external_id,
                    title=event.title,
                )
                return DedupResult(
                    event_id=duplicate_id,
                    venue_id=venue_id,
                    artist_ids=artist_ids,
                    merged_cross_source=True,
                )

        event_id = await upsert_event(conn, event, venue_id)
        artist_ids, _ = await link_lineup(conn, event_id, event.artists, prune=True)

        old_status: str | None = None
        # on_sale -> announced is the offsale mapping closing a sales window (the enum has
        # no off-sale value), not a real status regression, so it is not worth alerting on.
        if (
            previous_status is not None
            and previous_status != event.status
            and not (previous_status == "on_sale" and event.status == "announced")
        ):
            old_status = previous_status
            log.info(
                "event status changed",
                event_id=str(event_id),
                external_id=event.external_id,
                old_status=previous_status,
                new_status=event.status,
            )

        return DedupResult(
            event_id=event_id,
            venue_id=venue_id,
            artist_ids=artist_ids,
            is_new=previous_status is None,
            old_status=old_status,
        )
