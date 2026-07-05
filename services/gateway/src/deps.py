"""FastAPI dependencies: database sessions and JWT authentication."""

import uuid
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import get_settings
from src.models import User

_bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache
def get_engine() -> AsyncEngine:
    """Return the cached async database engine."""
    return create_async_engine(get_settings().database_url)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the cached async session factory."""
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped database session."""
    async with get_sessionmaker()() as session:
        yield session


def _unauthorized() -> HTTPException:
    """Build the standard 401 response for missing or invalid credentials."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid or missing credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Resolve the authenticated user from the request's Bearer JWT."""
    if credentials is None:
        raise _unauthorized()
    settings = get_settings()
    try:
        claims = jwt.decode(
            credentials.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        user_id = uuid.UUID(claims["sub"])
    except (JWTError, KeyError, ValueError) as exc:
        raise _unauthorized() from exc
    user = await session.get(User, user_id)
    if user is None:
        raise _unauthorized()
    return user


async def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """Resolve the authenticated user when a valid Bearer JWT is present, else None."""
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials, session)
    except HTTPException:
        return None


DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
