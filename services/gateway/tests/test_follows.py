"""Tests for POST/DELETE/GET /follows and taste-embedding recomputation."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import create_event

FUTURE = datetime.now(UTC) + timedelta(days=30)


async def _login(client: httpx.AsyncClient, email: str) -> tuple[str, dict[str, str]]:
    """Log in via /auth/dev, returning (user_id, auth headers)."""
    response = await client.post("/auth/dev", json={"email": email})
    assert response.status_code == 200
    body = response.json()
    return body["user"]["id"], {"Authorization": f"Bearer {body['token']}"}


async def _artist_id(client: httpx.AsyncClient, headers: dict[str, str], name: str) -> str:
    """Resolve a seeded artist's id through the search endpoint."""
    response = await client.get("/artists/search", params={"q": name}, headers=headers)
    matches = [r for r in response.json() if r["name"] == name]
    assert matches, f"artist {name!r} not found"
    return str(matches[0]["id"])


async def _taste_embedding(db: AsyncSession, user_id: str) -> str | None:
    """Fetch the user's raw taste_embedding value."""
    result = await db.execute(
        text("SELECT taste_embedding::text FROM users WHERE id = :id"), {"id": user_id}
    )
    value = result.scalar_one()
    return str(value) if value is not None else None


async def test_follows_require_auth(client: httpx.AsyncClient) -> None:
    """All follow endpoints reject unauthenticated requests with 401."""
    assert (await client.get("/follows")).status_code == 401
    assert (await client.post("/follows", json={"artist_id": str(uuid.uuid4())})).status_code == 401
    assert (await client.delete(f"/follows/{uuid.uuid4()}")).status_code == 401


async def test_follow_unknown_artist_returns_404(client: httpx.AsyncClient) -> None:
    """Following a nonexistent artist id fails with 404."""
    _, headers = await _login(client, "missing@example.com")
    response = await client.post("/follows", json={"artist_id": str(uuid.uuid4())}, headers=headers)
    assert response.status_code == 404


async def test_follow_lists_artist_and_sets_taste_embedding(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """Following an artist adds it to GET /follows and materializes a taste embedding."""
    user_id, headers = await _login(client, "follower@example.com")
    assert await _taste_embedding(db, user_id) is None

    artist_id = await _artist_id(client, headers, "Phoebe Bridgers")
    response = await client.post("/follows", json={"artist_id": artist_id}, headers=headers)
    assert response.status_code == 201
    body = response.json()
    assert body["id"] == artist_id
    assert body["followed"] is True

    follows = (await client.get("/follows", headers=headers)).json()
    assert [f["id"] for f in follows] == [artist_id]
    assert await _taste_embedding(db, user_id) is not None


async def test_follow_is_idempotent(client: httpx.AsyncClient) -> None:
    """Following the same artist twice succeeds and stores a single follow."""
    _, headers = await _login(client, "twice@example.com")
    artist_id = await _artist_id(client, headers, "Turnstile")
    first = await client.post("/follows", json={"artist_id": artist_id}, headers=headers)
    second = await client.post("/follows", json={"artist_id": artist_id}, headers=headers)
    assert first.status_code == second.status_code == 201
    follows = (await client.get("/follows", headers=headers)).json()
    assert len(follows) == 1


async def test_unfollow_removes_artist_and_clears_taste_embedding(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """Unfollowing the only followed artist empties GET /follows and nulls the embedding."""
    user_id, headers = await _login(client, "unfollower@example.com")
    artist_id = await _artist_id(client, headers, "Khruangbin")
    await client.post("/follows", json={"artist_id": artist_id}, headers=headers)
    assert await _taste_embedding(db, user_id) is not None

    response = await client.delete(f"/follows/{artist_id}", headers=headers)
    assert response.status_code == 204
    assert (await client.get("/follows", headers=headers)).json() == []
    assert await _taste_embedding(db, user_id) is None


async def test_unfollow_is_idempotent(client: httpx.AsyncClient) -> None:
    """Unfollowing an artist that is not followed still returns 204."""
    _, headers = await _login(client, "noop@example.com")
    artist_id = await _artist_id(client, headers, "Sylvan Esso")
    response = await client.delete(f"/follows/{artist_id}", headers=headers)
    assert response.status_code == 204


async def test_follow_reranks_feed(client: httpx.AsyncClient, db: AsyncSession) -> None:
    """After following an artist, that artist's event outranks others and scores above 0.7."""
    await create_event(db, starts_at=FUTURE, lineup=(("Phoebe Bridgers", 0),), title="PB Show")
    await create_event(db, starts_at=FUTURE, lineup=(("Denzel Curry", 0),), title="DC Show")
    _, headers = await _login(client, "ranker@example.com")

    baseline = (await client.get("/feed", headers=headers)).json()["items"]
    assert {item["score"] for item in baseline} == {0.5}

    artist_id = await _artist_id(client, headers, "Phoebe Bridgers")
    await client.post("/follows", json={"artist_id": artist_id}, headers=headers)

    ranked = (await client.get("/feed", headers=headers)).json()["items"]
    assert [item["artist_name"] for item in ranked] == ["Phoebe Bridgers", "Denzel Curry"]
    assert ranked[0]["score"] > 0.7
    assert ranked[1]["score"] < ranked[0]["score"]
