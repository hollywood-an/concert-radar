"""Tests for GET /feed."""

from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_headers, create_event, create_venue

FUTURE = datetime.now(UTC) + timedelta(days=30)


async def test_feed_requires_auth(client: httpx.AsyncClient) -> None:
    """GET /feed without a Bearer token is rejected with 401."""
    response = await client.get("/feed")
    assert response.status_code == 401


async def test_feed_returns_nearby_future_event(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """A future event at a seeded Columbus venue appears with numeric distance and score."""
    event_id = await create_event(db, starts_at=FUTURE)
    headers = await auth_headers(client, "feed@example.com")
    response = await client.get("/feed", headers=headers)
    assert response.status_code == 200
    page = response.json()
    assert page["has_more"] is False
    assert page["next_cursor"] is None
    assert len(page["items"]) == 1
    item = page["items"][0]
    assert item["event_id"] == str(event_id)
    assert item["venue_name"] == "Newport Music Hall"
    assert item["artist_name"] == "The National"
    assert isinstance(item["distance_m"], int | float)
    assert item["distance_m"] > 0
    assert 0 <= item["score"] <= 1


async def test_feed_excludes_event_outside_radius(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """An event at a venue beyond the user's travel radius is excluded."""
    await create_venue(db, name="Seattle Showbox", lon=-122.3350, lat=47.6080)
    await create_event(db, starts_at=FUTURE, venue_name="Seattle Showbox")
    headers = await auth_headers(client, "far@example.com")
    response = await client.get("/feed", headers=headers)
    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_feed_excludes_past_event(client: httpx.AsyncClient, db: AsyncSession) -> None:
    """An event that already started is excluded."""
    await create_event(db, starts_at=datetime.now(UTC) - timedelta(days=1))
    headers = await auth_headers(client, "past@example.com")
    response = await client.get("/feed", headers=headers)
    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_feed_excludes_cancelled_event(client: httpx.AsyncClient, db: AsyncSession) -> None:
    """A cancelled event is excluded."""
    await create_event(db, starts_at=FUTURE, status="cancelled")
    headers = await auth_headers(client, "cancelled@example.com")
    response = await client.get("/feed", headers=headers)
    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_feed_pagination_walks_all_items_without_duplicates(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """Walking the feed with limit=2 visits every event exactly once."""
    artists = ["The National", "Phoebe Bridgers", "Turnstile", "Japanese Breakfast", "Khruangbin"]
    created = {
        str(
            await create_event(
                db,
                starts_at=FUTURE + timedelta(days=i),
                lineup=((artist, 0),),
                title=f"Show {i}",
            )
        )
        for i, artist in enumerate(artists)
    }
    headers = await auth_headers(client, "pager@example.com")

    seen: list[str] = []
    cursor: str | None = None
    page_sizes: list[int] = []
    while True:
        params: dict[str, str | int] = {"limit": 2}
        if cursor is not None:
            params["cursor"] = cursor
        response = await client.get("/feed", params=params, headers=headers)
        assert response.status_code == 200
        page = response.json()
        page_sizes.append(len(page["items"]))
        seen.extend(item["event_id"] for item in page["items"])
        if not page["has_more"]:
            assert page["next_cursor"] is None
            break
        cursor = page["next_cursor"]
        assert cursor is not None

    assert page_sizes == [2, 2, 1]
    assert len(seen) == len(set(seen)) == 5
    assert set(seen) == created
