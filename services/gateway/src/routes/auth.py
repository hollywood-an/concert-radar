"""Development authentication endpoint (spec-sanctioned v1 substitute for Spotify OAuth)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from fastapi import APIRouter
from jose import jwt
from sqlalchemy import text

from src.config import Settings, get_settings
from src.deps import DbSession
from src.schemas import DevAuthRequest, DevAuthResponse, Location, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])
logger = structlog.get_logger()

_COLUMBUS_LON = -82.9988
_COLUMBUS_LAT = 39.9612

_INSERT_USER = text(
    """
    INSERT INTO users (email, display_name, home_location)
    VALUES (:email, :display_name, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography)
    ON CONFLICT (email) DO NOTHING
    RETURNING id
    """
)

_SELECT_USER = text(
    """
    SELECT id, email, display_name, travel_radius_m, created_at,
           ST_Y(home_location::geometry) AS lat,
           ST_X(home_location::geometry) AS lon
    FROM users
    WHERE email = :email
    """
)


def _mint_token(user_id: UUID, settings: Settings) -> str:
    """Create a signed JWT whose subject is the user id."""
    expires_at = datetime.now(UTC) + timedelta(hours=settings.jwt_expiry_hours)
    return jwt.encode(
        {"sub": str(user_id), "exp": expires_at},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


@router.post("/dev")
async def dev_login(payload: DevAuthRequest, session: DbSession) -> DevAuthResponse:
    """Get or create a user by email; new users default to downtown Columbus, OH
    (POINT -82.9988 39.9612) and the default travel radius so the dev feed is non-empty."""
    email = payload.email
    result = await session.execute(
        _INSERT_USER,
        {
            "email": email,
            "display_name": email.split("@", 1)[0],
            "lon": _COLUMBUS_LON,
            "lat": _COLUMBUS_LAT,
        },
    )
    created = result.scalar_one_or_none() is not None
    row = (await session.execute(_SELECT_USER, {"email": email})).mappings().one()
    await session.commit()
    if created:
        logger.info("user_created", user_id=str(row["id"]), email=email)

    location = None if row["lat"] is None else Location(lat=row["lat"], lon=row["lon"])
    user = UserOut(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        home_location=location,
        travel_radius_m=row["travel_radius_m"],
        created_at=row["created_at"],
    )
    return DevAuthResponse(token=_mint_token(user.id, get_settings()), user=user)
