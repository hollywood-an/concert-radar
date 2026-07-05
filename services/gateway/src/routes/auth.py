"""Authentication endpoints: dev email login and the Spotify OAuth + import flow."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException
from jose import JWTError, jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import Settings, get_settings
from src.deps import DbSession, OptionalUser
from src.kafka import get_taste_publisher
from src.routes.users import fetch_me
from src.schemas import (
    DevAuthRequest,
    DevAuthResponse,
    Location,
    SpotifyAuthResponse,
    SpotifyCallbackResponse,
    UserOut,
)
from src.spotify import SpotifyFollowedArtist, get_spotify_oauth

router = APIRouter(prefix="/auth", tags=["auth"])
logger = structlog.get_logger()

_STATE_PURPOSE = "spotify_oauth"
_STATE_TTL_MINUTES = 10

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


_STORE_SPOTIFY_SESSION = text(
    """
    UPDATE users
    SET spotify_id = :spotify_id,
        spotify_access_token = :access_token,
        spotify_refresh_token = coalesce(:refresh_token, spotify_refresh_token),
        updated_at = now()
    WHERE id = :id
    """
)

_ARTIST_BY_SPOTIFY_ID = text("SELECT id FROM artists WHERE spotify_id = :spotify_id")

_ARTIST_BY_NAME = text("SELECT id FROM artists WHERE lower(name) = lower(:name)")

# Only fill in metadata the row does not have yet; the enricher owns later updates.
_ARTIST_ATTACH_SPOTIFY = text(
    """
    UPDATE artists
    SET spotify_id = coalesce(spotify_id, :spotify_id),
        genres = CASE WHEN coalesce(cardinality(genres), 0) = 0 THEN :genres ELSE genres END,
        popularity = coalesce(popularity, :popularity),
        image_url = coalesce(image_url, :image_url),
        updated_at = now()
    WHERE id = :id
    """
)

_ARTIST_INSERT = text(
    """
    INSERT INTO artists (name, spotify_id, genres, popularity, image_url)
    VALUES (:name, :spotify_id, :genres, :popularity, :image_url)
    RETURNING id
    """
)

_INSERT_SPOTIFY_FOLLOW = text(
    """
    INSERT INTO follows (user_id, artist_id, source)
    VALUES (:user_id, :artist_id, 'spotify_import')
    ON CONFLICT (user_id, artist_id) DO NOTHING
    """
)

_RECOMPUTE_TASTE = text("SELECT update_user_taste_embedding(:user_id)")


def _mint_state(user_id: UUID | None, settings: Settings) -> str:
    """Sign a short-lived state token carrying the initiating user, if any."""
    expires_at = datetime.now(UTC) + timedelta(minutes=_STATE_TTL_MINUTES)
    claims = {"purpose": _STATE_PURPOSE, "exp": expires_at, "sub": str(user_id or "")}
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _read_state(state: str, settings: Settings) -> UUID | None:
    """Validate the state token and return the initiating user id, if any."""
    try:
        claims = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise HTTPException(status_code=400, detail="invalid state") from exc
    if claims.get("purpose") != _STATE_PURPOSE:
        raise HTTPException(status_code=400, detail="invalid state")
    subject = claims.get("sub") or ""
    return UUID(subject) if subject else None


@router.post("/spotify")
async def spotify_login(user: OptionalUser) -> SpotifyAuthResponse:
    """Return the Spotify authorize URL. 503 until Spotify credentials are configured."""
    oauth = get_spotify_oauth()
    if not oauth.enabled:
        raise HTTPException(status_code=503, detail="spotify credentials not configured")
    state = _mint_state(user.id if user else None, get_settings())
    return SpotifyAuthResponse(authorize_url=oauth.authorize_url(state))


async def _upsert_import_artist(session: AsyncSession, artist: SpotifyFollowedArtist) -> UUID:
    """Match an imported artist by spotify_id, then name, else insert; return its id."""
    row = (await session.execute(_ARTIST_BY_SPOTIFY_ID, {"spotify_id": artist.spotify_id})).first()
    if row is not None:
        return UUID(str(row[0]))
    params = {
        "name": artist.name,
        "spotify_id": artist.spotify_id,
        "genres": artist.genres,
        "popularity": artist.popularity,
        "image_url": artist.image_url,
    }
    row = (await session.execute(_ARTIST_BY_NAME, {"name": artist.name})).first()
    if row is not None:
        artist_id = UUID(str(row[0]))
        await session.execute(_ARTIST_ATTACH_SPOTIFY, {**params, "id": artist_id})
        return artist_id
    inserted = (await session.execute(_ARTIST_INSERT, params)).one()
    return UUID(str(inserted[0]))


@router.get("/spotify/callback")
async def spotify_callback(code: str, state: str, session: DbSession) -> SpotifyCallbackResponse:
    """Exchange the OAuth code, link the Spotify account, and import followed artists."""
    settings = get_settings()
    oauth = get_spotify_oauth()
    if not oauth.enabled:
        raise HTTPException(status_code=503, detail="spotify credentials not configured")
    initiating_user_id = _read_state(state, settings)

    access_token, refresh_token = await oauth.exchange_code(code)
    profile = await oauth.get_profile(access_token)

    if initiating_user_id is not None:
        user_id = initiating_user_id
    else:
        await session.execute(
            _INSERT_USER,
            {
                "email": profile.email,
                "display_name": profile.display_name or profile.email.split("@", 1)[0],
                "lon": _COLUMBUS_LON,
                "lat": _COLUMBUS_LAT,
            },
        )
        row = (await session.execute(_SELECT_USER, {"email": profile.email})).mappings().one()
        user_id = row["id"]

    await session.execute(
        _STORE_SPOTIFY_SESSION,
        {
            "id": user_id,
            "spotify_id": profile.spotify_id,
            "access_token": access_token,
            "refresh_token": refresh_token,
        },
    )

    followed = await oauth.get_followed_artists(access_token)
    for artist in followed:
        artist_id = await _upsert_import_artist(session, artist)
        await session.execute(_INSERT_SPOTIFY_FOLLOW, {"user_id": user_id, "artist_id": artist_id})
    await session.execute(_RECOMPUTE_TASTE, {"user_id": user_id})
    await session.commit()
    await get_taste_publisher().publish(user_id)
    logger.info(
        "spotify_import_complete",
        user_id=str(user_id),
        spotify_id=profile.spotify_id,
        imported_artists=len(followed),
    )

    return SpotifyCallbackResponse(
        token=_mint_token(user_id, settings),
        user=await fetch_me(session, user_id),
        imported_artists=len(followed),
    )
