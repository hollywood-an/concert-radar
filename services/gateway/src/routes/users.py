"""Current-user endpoints: GET /me and PATCH /me."""

from uuid import UUID

import structlog
from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.deps import CurrentUser, DbSession
from src.schemas import Location, UserOut, UserUpdate

router = APIRouter(tags=["users"])
logger = structlog.get_logger()

_SELECT_ME = text(
    """
    SELECT id, email, display_name, travel_radius_m, alert_email,
           quiet_hours_start, quiet_hours_end, created_at,
           ST_Y(home_location::geometry) AS lat,
           ST_X(home_location::geometry) AS lon
    FROM users
    WHERE id = :id
    """
)

# Whitelisted SET fragments; PATCH only touches fields present in the request body.
_SET_FRAGMENTS = {
    "display_name": "display_name = :display_name",
    "home_location": ("home_location = ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography"),
    "travel_radius_m": "travel_radius_m = :travel_radius_m",
    "alert_email": "alert_email = :alert_email",
    "quiet_hours_start": "quiet_hours_start = :quiet_hours_start",
    "quiet_hours_end": "quiet_hours_end = :quiet_hours_end",
}


async def fetch_me(session: AsyncSession, user_id: UUID) -> UserOut:
    """Load the current user's public view."""
    row = (await session.execute(_SELECT_ME, {"id": user_id})).mappings().one()
    location = None if row["lat"] is None else Location(lat=row["lat"], lon=row["lon"])
    return UserOut(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        home_location=location,
        travel_radius_m=row["travel_radius_m"],
        alert_email=row["alert_email"],
        quiet_hours_start=row["quiet_hours_start"],
        quiet_hours_end=row["quiet_hours_end"],
        created_at=row["created_at"],
    )


@router.get("/me")
async def get_me(user: CurrentUser, session: DbSession) -> UserOut:
    """Return the authenticated user's profile."""
    return await fetch_me(session, user.id)


@router.patch("/me")
async def update_me(payload: UserUpdate, user: CurrentUser, session: DbSession) -> UserOut:
    """Update the fields present in the request body and return the fresh profile."""
    sets: list[str] = []
    params: dict[str, object] = {"id": user.id}
    for field in payload.model_fields_set:
        value = getattr(payload, field)
        if field == "home_location":
            if value is None:
                sets.append("home_location = NULL")
            else:
                sets.append(_SET_FRAGMENTS[field])
                params["lon"] = value.lon
                params["lat"] = value.lat
        else:
            sets.append(_SET_FRAGMENTS[field])
            params[field] = value
    if sets:
        sets.append("updated_at = now()")
        await session.execute(text(f"UPDATE users SET {', '.join(sets)} WHERE id = :id"), params)
        await session.commit()
        logger.info("user_updated", user_id=str(user.id), fields=sorted(payload.model_fields_set))
    return await fetch_me(session, user.id)
