"""Tests for GET /artists/search."""

import httpx

from tests.conftest import auth_headers


async def test_search_requires_auth(client: httpx.AsyncClient) -> None:
    """GET /artists/search without a Bearer token is rejected with 401."""
    response = await client.get("/artists/search", params={"q": "phoebe"})
    assert response.status_code == 401


async def test_search_finds_seeded_artist_by_prefix(client: httpx.AsyncClient) -> None:
    """A short prefix query matches the seeded artist case-insensitively."""
    headers = await auth_headers(client, "search@example.com")
    response = await client.get("/artists/search", params={"q": "phoe"}, headers=headers)
    assert response.status_code == 200
    results = response.json()
    assert results, "expected at least one match"
    top = results[0]
    assert top["name"] == "Phoebe Bridgers"
    assert top["followed"] is False
    assert isinstance(top["genres"], list)


async def test_search_tolerates_fuzzy_query(client: httpx.AsyncClient) -> None:
    """A misspelled query still finds the artist via trigram similarity."""
    headers = await auth_headers(client, "fuzzy@example.com")
    response = await client.get("/artists/search", params={"q": "kruangbin"}, headers=headers)
    assert response.status_code == 200
    assert "Khruangbin" in [r["name"] for r in response.json()]


async def test_search_caps_results_at_ten(client: httpx.AsyncClient) -> None:
    """A broad query never returns more than 10 artists."""
    headers = await auth_headers(client, "broad@example.com")
    response = await client.get("/artists/search", params={"q": "e"}, headers=headers)
    assert response.status_code == 200
    assert len(response.json()) <= 10


async def test_search_marks_followed_artists(client: httpx.AsyncClient) -> None:
    """After following an artist, search results flag it as followed."""
    headers = await auth_headers(client, "flagged@example.com")
    search = await client.get("/artists/search", params={"q": "turnstile"}, headers=headers)
    artist_id = search.json()[0]["id"]
    followed = await client.post("/follows", json={"artist_id": artist_id}, headers=headers)
    assert followed.status_code == 201
    again = await client.get("/artists/search", params={"q": "turnstile"}, headers=headers)
    assert again.json()[0]["followed"] is True
