"""Pydantic request and response schemas for the gateway API."""

from datetime import datetime, time
from uuid import UUID

from pydantic import BaseModel, Field


class DevAuthRequest(BaseModel):
    """Body of POST /auth/dev."""

    email: str = Field(min_length=3, pattern=r"^[^@\s]+@[^@\s]+$")


class Location(BaseModel):
    """A WGS84 point as latitude and longitude."""

    lat: float
    lon: float


class UserOut(BaseModel):
    """Public view of a user row."""

    id: UUID
    email: str
    display_name: str | None
    home_location: Location | None
    travel_radius_m: int
    alert_email: bool = True
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None
    created_at: datetime


class UserUpdate(BaseModel):
    """Body of PATCH /me; only fields present in the request are updated."""

    display_name: str | None = None
    home_location: Location | None = None
    travel_radius_m: int | None = Field(default=None, ge=1000, le=500_000)
    alert_email: bool | None = None
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None


class DevAuthResponse(BaseModel):
    """Response of POST /auth/dev: a JWT plus the user it authenticates."""

    token: str
    user: UserOut


class ArtistSummary(BaseModel):
    """An artist as returned by search and follow endpoints, with follow state."""

    id: UUID
    name: str
    image_url: str | None
    genres: list[str]
    followed: bool


class FollowRequest(BaseModel):
    """Body of POST /follows."""

    artist_id: UUID


class FeedItem(BaseModel):
    """One ranked event in the user's feed."""

    event_id: UUID
    title: str | None
    starts_at: datetime
    status: str
    price_min_cents: int | None
    price_max_cents: int | None
    source_url: str | None
    image_url: str | None
    venue_name: str
    venue_city: str | None
    venue_lat: float
    venue_lon: float
    distance_m: float
    artist_id: UUID
    artist_name: str
    artist_image_url: str | None
    artist_genres: list[str]
    score: float


class FeedPage(BaseModel):
    """A page of feed items with opaque-cursor pagination."""

    items: list[FeedItem]
    next_cursor: str | None
    has_more: bool


class VenueOut(BaseModel):
    """Venue details embedded in an event response."""

    id: UUID
    name: str
    city: str | None
    state: str | None
    location: Location


class EventArtistOut(BaseModel):
    """One lineup entry on an event, ordered by billing."""

    id: UUID
    name: str
    image_url: str | None
    genres: list[str]
    billing: int


class EventDetail(BaseModel):
    """Full event details with venue and lineup."""

    id: UUID
    title: str | None
    starts_at: datetime
    doors_at: datetime | None
    on_sale_at: datetime | None
    price_min_cents: int | None
    price_max_cents: int | None
    currency: str | None
    status: str
    source: str
    source_url: str | None
    image_url: str | None
    venue: VenueOut
    artists: list[EventArtistOut]
