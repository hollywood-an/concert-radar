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


async def test_feed_items_carry_coordinates_and_genres(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """Feed items expose venue coordinates and headliner genres for the map and filters."""
    await create_event(db, starts_at=FUTURE)
    headers = await auth_headers(client, "coords@example.com")
    item = (await client.get("/feed", headers=headers)).json()["items"][0]
    assert abs(item["venue_lat"] - 39.9979) < 0.001
    assert abs(item["venue_lon"] - -83.0083) < 0.001
    assert "indie rock" in item["artist_genres"]


async def test_feed_genre_filter_is_case_insensitive(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """Filtering by genre keeps matching headliners and drops the rest."""
    await create_event(db, starts_at=FUTURE, lineup=(("The National", 0),))
    await create_event(db, starts_at=FUTURE, lineup=(("Denzel Curry", 0),), title="Rap Show")
    headers = await auth_headers(client, "genre@example.com")

    response = await client.get("/feed", params={"genres": ["Hip Hop"]}, headers=headers)
    items = response.json()["items"]
    assert [i["artist_name"] for i in items] == ["Denzel Curry"]


async def test_feed_price_filter_drops_expensive_and_unpriced(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """A max price keeps only events whose min price is known and under the cap."""
    await create_event(db, starts_at=FUTURE)  # price_min 2500
    headers = await auth_headers(client, "price@example.com")
    assert (
        len(
            (await client.get("/feed", params={"max_price_cents": 3000}, headers=headers)).json()[
                "items"
            ]
        )
        == 1
    )
    assert (await client.get("/feed", params={"max_price_cents": 1000}, headers=headers)).json()[
        "items"
    ] == []


async def test_feed_date_and_distance_filters(client: httpx.AsyncClient, db: AsyncSession) -> None:
    """Date windows and a distance cap narrow the feed."""
    await create_event(db, starts_at=FUTURE, title="Soon Show")
    await create_event(db, starts_at=FUTURE + timedelta(days=40), title="Later Show")
    headers = await auth_headers(client, "window@example.com")

    in_window = await client.get(
        "/feed",
        params={
            "date_from": (FUTURE - timedelta(days=1)).isoformat(),
            "date_to": (FUTURE + timedelta(days=1)).isoformat(),
        },
        headers=headers,
    )
    assert [i["title"] for i in in_window.json()["items"]] == ["Soon Show"]

    # Newport Music Hall is a few km from the default home point.
    near = await client.get("/feed", params={"max_distance_m": 10000}, headers=headers)
    assert len(near.json()["items"]) == 2
    tight = await client.get("/feed", params={"max_distance_m": 100}, headers=headers)
    assert tight.json()["items"] == []


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
