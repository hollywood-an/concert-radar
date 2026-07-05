"""Event detail and dismissal endpoints."""

from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select, text
from sqlalchemy.orm import joinedload, selectinload

from src.deps import CurrentUser, DbSession
from src.models import Event, EventArtist
from src.schemas import EventArtistOut, EventDetail, Location, VenueOut

router = APIRouter(tags=["events"])
logger = structlog.get_logger()

_VENUE_COORDS_SQL = text(
    "SELECT ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon"
    " FROM venues WHERE id = :venue_id"
)

_INSERT_DISMISSAL = text(
    "INSERT INTO dismissals (user_id, event_id) VALUES (:user_id, :event_id) ON CONFLICT DO NOTHING"
)


@router.post("/events/{event_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_event(event_id: UUID, user: CurrentUser, session: DbSession) -> Response:
    """Hide an event from the user's future feeds. Idempotent."""
    event = await session.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    await session.execute(_INSERT_DISMISSAL, {"user_id": user.id, "event_id": event_id})
    await session.commit()
    logger.info("event_dismissed", user_id=str(user.id), event_id=str(event_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/events/{event_id}")
async def get_event(event_id: UUID, session: DbSession) -> EventDetail:
    """Return full event details with venue info and lineup ordered by billing."""
    stmt = (
        select(Event)
        .where(Event.id == event_id)
        .options(
            joinedload(Event.venue),
            selectinload(Event.event_artists).joinedload(EventArtist.artist),
        )
    )
    event = (await session.execute(stmt)).scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    coords_result = await session.execute(_VENUE_COORDS_SQL, {"venue_id": event.venue_id})
    coords = coords_result.mappings().one()
    return EventDetail(
        id=event.id,
        title=event.title,
        starts_at=event.starts_at,
        doors_at=event.doors_at,
        on_sale_at=event.on_sale_at,
        price_min_cents=event.price_min_cents,
        price_max_cents=event.price_max_cents,
        currency=event.currency,
        status=event.status,
        source=event.source,
        source_url=event.source_url,
        image_url=event.image_url,
        venue=VenueOut(
            id=event.venue.id,
            name=event.venue.name,
            city=event.venue.city,
            state=event.venue.state,
            location=Location(lat=coords["lat"], lon=coords["lon"]),
        ),
        artists=[
            EventArtistOut(
                id=link.artist.id,
                name=link.artist.name,
                image_url=link.artist.image_url,
                genres=list(link.artist.genres or []),
                billing=link.billing,
            )
            for link in event.event_artists
        ],
    )
