"""Message contracts for the topics the enricher consumes and produces."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DedupedEvent(BaseModel):
    """Payload of events.deduped, as published by the deduper."""

    event_id: UUID
    venue_id: UUID
    artist_ids: list[UUID]
    source: str
    external_id: str
    title: str
    starts_at: datetime
    status: str
    is_new: bool


class EnrichedEvent(BaseModel):
    """Payload of events.enriched: the event with its artists resolved and embedded."""

    event_id: UUID
    venue_id: UUID
    artist_ids: list[UUID]
    enriched_artist_ids: list[UUID]
    title: str
    starts_at: datetime
    status: str
