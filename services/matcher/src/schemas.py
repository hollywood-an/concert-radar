"""Message contracts for the topics the matcher consumes and produces."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class EnrichedEvent(BaseModel):
    """Payload of events.enriched, as published by the enricher."""

    event_id: UUID
    venue_id: UUID
    artist_ids: list[UUID]
    enriched_artist_ids: list[UUID]
    title: str
    starts_at: datetime
    status: str


class TasteUpdated(BaseModel):
    """Payload of users.taste_updated, as published by the gateway."""

    user_id: UUID


class MatchProposed(BaseModel):
    """Payload of matches.proposed: one user who should hear about one event."""

    user_id: UUID
    event_id: UUID
    score: float
