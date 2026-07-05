"""Tests for GET /me and PATCH /me."""

from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_headers, create_event


async def test_me_requires_auth(client: httpx.AsyncClient) -> None:
    """Both /me endpoints reject unauthenticated requests with 401."""
    assert (await client.get("/me")).status_code == 401
    assert (await client.patch("/me", json={})).status_code == 401


async def test_get_me_returns_dev_defaults(client: httpx.AsyncClient) -> None:
    """A fresh dev user has the Columbus default location, radius, and alert prefs."""
    headers = await auth_headers(client, "me@example.com")
    response = await client.get("/me", headers=headers)
    assert response.status_code == 200
    me = response.json()
    assert me["email"] == "me@example.com"
    assert me["travel_radius_m"] == 80467
    assert me["alert_email"] is True
    assert me["quiet_hours_start"] is None
    assert round(me["home_location"]["lat"], 4) == 39.9612
    assert round(me["home_location"]["lon"], 4) == -82.9988


async def test_patch_updates_only_provided_fields(client: httpx.AsyncClient) -> None:
    """PATCH applies present fields and leaves the rest untouched."""
    headers = await auth_headers(client, "patch@example.com")
    response = await client.patch(
        "/me",
        json={
            "home_location": {"lat": 40.1, "lon": -83.2},
            "travel_radius_m": 25000,
            "quiet_hours_start": "22:00:00",
            "quiet_hours_end": "07:00:00",
        },
        headers=headers,
    )
    assert response.status_code == 200
    me = response.json()
    assert round(me["home_location"]["lat"], 4) == 40.1
    assert round(me["home_location"]["lon"], 4) == -83.2
    assert me["travel_radius_m"] == 25000
    assert me["quiet_hours_start"] == "22:00:00"
    assert me["alert_email"] is True

    second = await client.patch("/me", json={"alert_email": False}, headers=headers)
    me = second.json()
    assert me["alert_email"] is False
    assert me["travel_radius_m"] == 25000
    assert me["quiet_hours_start"] == "22:00:00"


async def test_patch_can_clear_quiet_hours(client: httpx.AsyncClient) -> None:
    """Sending explicit nulls clears the quiet-hours window."""
    headers = await auth_headers(client, "clear@example.com")
    await client.patch(
        "/me",
        json={"quiet_hours_start": "22:00:00", "quiet_hours_end": "07:00:00"},
        headers=headers,
    )
    response = await client.patch(
        "/me", json={"quiet_hours_start": None, "quiet_hours_end": None}, headers=headers
    )
    me = response.json()
    assert me["quiet_hours_start"] is None
    assert me["quiet_hours_end"] is None


async def test_patch_rejects_absurd_radius(client: httpx.AsyncClient) -> None:
    """The travel radius is validated to a sane range."""
    headers = await auth_headers(client, "radius@example.com")
    response = await client.patch("/me", json={"travel_radius_m": 10}, headers=headers)
    assert response.status_code == 422


async def test_location_change_moves_the_feed(client: httpx.AsyncClient, db: AsyncSession) -> None:
    """Moving home far away empties the feed; moving back restores it."""
    await create_event(db, starts_at=datetime.now(UTC) + timedelta(days=30))
    headers = await auth_headers(client, "mover@example.com")

    assert len((await client.get("/feed", headers=headers)).json()["items"]) == 1
    await client.patch(
        "/me", json={"home_location": {"lat": 47.608, "lon": -122.335}}, headers=headers
    )
    assert (await client.get("/feed", headers=headers)).json()["items"] == []
    await client.patch(
        "/me", json={"home_location": {"lat": 39.9612, "lon": -82.9988}}, headers=headers
    )
    assert len((await client.get("/feed", headers=headers)).json()["items"]) == 1
