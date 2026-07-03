"""Tests for POST /auth/dev."""

import httpx
import pytest
from jose import jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_dev_auth_creates_columbus_user(client: httpx.AsyncClient, db: AsyncSession) -> None:
    """A new email creates a user homed in downtown Columbus and returns a decodable JWT."""
    response = await client.post("/auth/dev", json={"email": "ada@example.com"})
    assert response.status_code == 200
    body = response.json()

    from src.config import get_settings

    settings = get_settings()
    claims = jwt.decode(body["token"], settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    assert claims["sub"] == body["user"]["id"]

    row = (
        (
            await db.execute(
                text(
                    """
                    SELECT display_name, travel_radius_m,
                           ST_X(home_location::geometry) AS lon,
                           ST_Y(home_location::geometry) AS lat
                    FROM users WHERE email = 'ada@example.com'
                    """
                )
            )
        )
        .mappings()
        .one()
    )
    assert row["display_name"] == "ada"
    assert row["travel_radius_m"] == 80467
    assert row["lon"] == pytest.approx(-82.9988)
    assert row["lat"] == pytest.approx(39.9612)
    assert body["user"]["home_location"]["lat"] == pytest.approx(39.9612)
    assert body["user"]["home_location"]["lon"] == pytest.approx(-82.9988)


async def test_dev_auth_same_email_returns_same_user(client: httpx.AsyncClient) -> None:
    """Calling /auth/dev twice with one email yields the same user id both times."""
    first = await client.post("/auth/dev", json={"email": "repeat@example.com"})
    second = await client.post("/auth/dev", json={"email": "repeat@example.com"})
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["user"]["id"] == second.json()["user"]["id"]
