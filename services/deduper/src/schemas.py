"""Message contracts for the topics the deduper consumes and produces."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DiscoveredArtist(BaseModel):
    """One lineup entry on a discovered event (0 = headliner)."""

    name: str
    tm_id: str = ""
    genres: list[str] = Field(default_factory=list)
    billing: int


class DiscoveredVenue(BaseModel):
    """The venue on a discovered event, with the source's own venue id in tm_id."""

    tm_id: str
    name: str
    city: str | None = None
    state: str | None = None
    country: str | None = None
    address: dict[str, str] = Field(default_factory=dict)
    longitude: float
    latitude: float


class DiscoveredEvent(BaseModel):
    """Payload of events.discovered, as published by the scrapers."""

    source: str
    external_id: str
    title: str
    source_url: str | None = None
    starts_at: datetime
    doors_at: datetime | None = None
    on_sale_at: datetime | None = None
    price_min_cents: int | None = None
    price_max_cents: int | None = None
    currency: str = "USD"
    image_url: str | None = None
    status: str
    venue: DiscoveredVenue
    artists: list[DiscoveredArtist] = Field(default_factory=list)


class DedupedEvent(BaseModel):
    """Payload of events.deduped: the canonical event row a discovery resolved to."""

    event_id: UUID
    venue_id: UUID
    artist_ids: list[UUID]
    source: str
    external_id: str
    title: str
    starts_at: datetime
    status: str
    is_new: bool


class StatusChange(BaseModel):
    """Payload of events.status_changed."""

    event_id: UUID
    source: str
    external_id: str
    old_status: str
    new_status: str
