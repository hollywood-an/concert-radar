"""Tests for GET /me and PATCH /me."""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
from aiokafka import AIOKafkaConsumer
from sqlalchemy.ext.asyncio import AsyncSession

from src.kafka import USERS_TASTE_UPDATED_TOPIC
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
    assert "quiet_hours_start" not in me
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
            "display_name": "Patched",
        },
        headers=headers,
    )
    assert response.status_code == 200
    me = response.json()
    assert round(me["home_location"]["lat"], 4) == 40.1
    assert round(me["home_location"]["lon"], 4) == -83.2
    assert me["travel_radius_m"] == 25000
    assert me["display_name"] == "Patched"
    assert me["alert_email"] is True

    second = await client.patch("/me", json={"alert_email": False}, headers=headers)
    me = second.json()
    assert me["alert_email"] is False
    assert me["travel_radius_m"] == 25000
    assert me["display_name"] == "Patched"


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


async def test_area_change_rematches_every_followed_artist(
    client: httpx.AsyncClient, kafka_bootstrap: str
) -> None:
    """Moving home or changing the radius republishes all follows; other edits publish nothing."""
    login = (await client.post("/auth/dev", json={"email": "relocator@example.com"})).json()
    user_id = login["user"]["id"]
    headers = {"Authorization": f"Bearer {login['token']}"}
    followed: list[str] = []
    for name in ("Phoebe Bridgers", "Turnstile"):
        hits = (await client.get("/artists/search", params={"q": name}, headers=headers)).json()
        artist_id = next(a["id"] for a in hits if a["name"] == name)
        await client.post("/follows", json={"artist_id": artist_id}, headers=headers)
        followed.append(artist_id)

    await client.patch("/me", json={"display_name": "Renamed"}, headers=headers)
    await client.patch(
        "/me", json={"home_location": {"lat": 41.4993, "lon": -81.6944}}, headers=headers
    )
    await client.patch("/me", json={"travel_radius_m": 120_000}, headers=headers)

    consumer = AIOKafkaConsumer(
        USERS_TASTE_UPDATED_TOPIC, bootstrap_servers=kafka_bootstrap, auto_offset_reset="earliest"
    )
    published: list[list[str]] = []

    async def drain(timeout_ms: int) -> None:
        for records in (await consumer.getmany(timeout_ms=timeout_ms)).values():
            published.extend(
                json.loads(r.value)["followed_artist_ids"]
                for r in records
                if r.key == user_id.encode()
            )

    await consumer.start()
    try:
        deadline = asyncio.get_running_loop().time() + 15
        while len(published) < 4 and asyncio.get_running_loop().time() < deadline:
            await drain(1_000)
        await drain(2_000)
    finally:
        await consumer.stop()

    # Two follows, then the move and the radius change; the rename publishes nothing.
    assert published[:2] == [[followed[0]], [followed[1]]]
    assert len(published) == 4
    assert all(set(ids) == set(followed) for ids in published[2:])
