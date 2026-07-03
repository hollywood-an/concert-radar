"""SQLAlchemy ORM models mirroring the Concert Radar database schema."""

import uuid
from datetime import datetime, time
from typing import Any

from geoalchemy2 import Geography, WKBElement
from pgvector.sqlalchemy import Vector
from sqlalchemy import TIMESTAMP, ForeignKey, Text
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EVENT_STATUS = ENUM(
    "announced",
    "on_sale",
    "sold_out",
    "cancelled",
    "rescheduled",
    "postponed",
    name="event_status",
    create_type=False,
)


class Base(DeclarativeBase):
    """Declarative base mapping datetime annotations to timestamptz columns."""

    type_annotation_map = {datetime: TIMESTAMP(timezone=True)}


class Artist(Base):
    """Row in the artists table."""

    __tablename__ = "artists"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    name: Mapped[str]
    mbid: Mapped[str | None]
    spotify_id: Mapped[str | None]
    genres: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    embedding: Mapped[Any] = mapped_column(Vector(384), nullable=True)
    popularity: Mapped[int | None]
    image_url: Mapped[str | None]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class Venue(Base):
    """Row in the venues table."""

    __tablename__ = "venues"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    name: Mapped[str]
    location: Mapped[WKBElement] = mapped_column(Geography(geometry_type="POINT", srid=4326))
    address: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    city: Mapped[str | None]
    state: Mapped[str | None]
    country: Mapped[str | None]
    capacity: Mapped[int | None]
    source_ids: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime]


class Event(Base):
    """Row in the events table."""

    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    venue_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("venues.id"))
    title: Mapped[str | None]
    starts_at: Mapped[datetime]
    doors_at: Mapped[datetime | None]
    on_sale_at: Mapped[datetime | None]
    price_min_cents: Mapped[int | None]
    price_max_cents: Mapped[int | None]
    currency: Mapped[str | None]
    status: Mapped[str] = mapped_column(EVENT_STATUS)
    source: Mapped[str]
    external_id: Mapped[str]
    source_url: Mapped[str | None]
    image_url: Mapped[str | None]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    venue: Mapped[Venue] = relationship()
    event_artists: Mapped[list["EventArtist"]] = relationship(order_by="EventArtist.billing")


class EventArtist(Base):
    """Row in the event_artists lineup table."""

    __tablename__ = "event_artists"

    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id"), primary_key=True)
    artist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artists.id"), primary_key=True)
    billing: Mapped[int]

    artist: Mapped[Artist] = relationship()


class User(Base):
    """Row in the users table."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    email: Mapped[str]
    display_name: Mapped[str | None]
    spotify_id: Mapped[str | None]
    spotify_access_token: Mapped[str | None]
    spotify_refresh_token: Mapped[str | None]
    home_location: Mapped[WKBElement | None] = mapped_column(
        Geography(geometry_type="POINT", srid=4326)
    )
    travel_radius_m: Mapped[int]
    taste_embedding: Mapped[Any] = mapped_column(Vector(384), nullable=True)
    alert_email: Mapped[bool]
    quiet_hours_start: Mapped[time | None]
    quiet_hours_end: Mapped[time | None]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
