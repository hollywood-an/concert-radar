"""Tests for GET /artists/search and GET /artists/{id}."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_headers, create_event

FUTURE = datetime.now(UTC) + timedelta(days=30)


async def seeded_artist_id(session: AsyncSession, name: str) -> str:
    """Return the id of the seeded artist with this name."""
    found = await session.execute(text("SELECT id FROM artists WHERE name = :name"), {"name": name})
    return str(found.scalar_one())


@pytest.fixture
async def unembedded_artist(db: AsyncSession) -> AsyncIterator[str]:
    """Insert an indie rock artist with no embedding, deleting it after the test."""
    inserted = await db.execute(
        text(
            "INSERT INTO artists (name, genres) VALUES ('Unembedded Band', ARRAY['indie rock'])"
            " RETURNING id"
        )
    )
    new_id = str(inserted.scalar_one())
    await db.commit()
    yield new_id
    await db.execute(text("DELETE FROM artists WHERE id = :id"), {"id": new_id})
    await db.commit()


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


async def test_artist_detail_requires_auth(client: httpx.AsyncClient, db: AsyncSession) -> None:
    """GET /artists/{id} without a Bearer token is rejected with 401."""
    response = await client.get(f"/artists/{await seeded_artist_id(db, 'Phoebe Bridgers')}")
    assert response.status_code == 401


async def test_artist_detail_unknown_id_returns_404(client: httpx.AsyncClient) -> None:
    """An unknown artist id yields 404."""
    headers = await auth_headers(client, "artist404@example.com")
    response = await client.get(f"/artists/{uuid.uuid4()}", headers=headers)
    assert response.status_code == 404


async def test_artist_detail_returns_profile_and_follow_state(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """The detail carries the artist's name and genres and reflects the viewer's follow."""
    phoebe = await seeded_artist_id(db, "Phoebe Bridgers")
    headers = await auth_headers(client, "profile@example.com")
    before = await client.get(f"/artists/{phoebe}", headers=headers)
    assert before.status_code == 200
    body = before.json()
    assert body["id"] == phoebe
    assert body["name"] == "Phoebe Bridgers"
    assert body["genres"] == ["indie folk", "indie rock", "singer-songwriter"]
    assert body["image_url"] is None
    assert body["followed"] is False

    await client.post("/follows", json={"artist_id": phoebe}, headers=headers)
    after = await client.get(f"/artists/{phoebe}", headers=headers)
    assert after.json()["followed"] is True


async def test_artist_upcoming_lists_future_shows_at_any_billing_by_date(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """Upcoming shows include supporting slots, sorted by date, with price and distance."""
    later = await create_event(
        db, starts_at=FUTURE + timedelta(days=10), lineup=(("Phoebe Bridgers", 0),), title="Later"
    )
    sooner = await create_event(
        db,
        starts_at=FUTURE,
        status="on_sale",
        venue_name="Ace of Cups",
        lineup=(("The National", 0), ("Phoebe Bridgers", 1)),
        title="Sooner",
    )
    headers = await auth_headers(client, "upcoming@example.com")
    response = await client.get(
        f"/artists/{await seeded_artist_id(db, 'Phoebe Bridgers')}", headers=headers
    )
    upcoming = response.json()["upcoming"]
    assert [show["event_id"] for show in upcoming] == [str(sooner), str(later)]
    first = upcoming[0]
    assert first["title"] == "Sooner"
    assert first["venue_name"] == "Ace of Cups"
    assert first["venue_city"] == "Columbus"
    assert first["price_min_cents"] == 2500
    assert first["price_max_cents"] == 4500
    assert first["dismissed"] is False
    # The dev user lives downtown; Ace of Cups is about 6 km north.
    assert 5000 < first["distance_m"] < 7000


async def test_artist_upcoming_excludes_past_and_inactive_shows(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """Past, cancelled, and postponed shows are left out of upcoming."""
    await create_event(db, starts_at=datetime.now(UTC) - timedelta(days=1), title="Past")
    await create_event(db, starts_at=FUTURE, status="cancelled", title="Cancelled")
    await create_event(db, starts_at=FUTURE, status="postponed", title="Postponed")
    kept = await create_event(db, starts_at=FUTURE, title="Kept")
    headers = await auth_headers(client, "inactive@example.com")
    response = await client.get(
        f"/artists/{await seeded_artist_id(db, 'The National')}", headers=headers
    )
    assert [show["event_id"] for show in response.json()["upcoming"]] == [str(kept)]


async def test_artist_upcoming_flags_dismissed_shows(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """A show the viewer dismissed stays listed but is flagged as dismissed."""
    event_id = await create_event(db, starts_at=FUTURE)
    headers = await auth_headers(client, "flag-dismissed@example.com")
    await client.post(f"/events/{event_id}/dismiss", headers=headers)
    response = await client.get(
        f"/artists/{await seeded_artist_id(db, 'The National')}", headers=headers
    )
    assert [show["dismissed"] for show in response.json()["upcoming"]] == [True]


async def test_artist_upcoming_distance_is_null_without_home_location(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """A user who cleared their home location gets shows with a null distance."""
    await create_event(db, starts_at=FUTURE)
    headers = await auth_headers(client, "homeless@example.com")
    cleared = await client.patch("/me", json={"home_location": None}, headers=headers)
    assert cleared.json()["home_location"] is None
    response = await client.get(
        f"/artists/{await seeded_artist_id(db, 'The National')}", headers=headers
    )
    assert [show["distance_m"] for show in response.json()["upcoming"]] == [None]


async def test_similar_artists_rank_by_embedding_distance(
    client: httpx.AsyncClient, db: AsyncSession, unembedded_artist: str
) -> None:
    """Similar artists are the six nearest by genre embedding, never self or unembedded."""
    phoebe = await seeded_artist_id(db, "Phoebe Bridgers")
    headers = await auth_headers(client, "similar@example.com")
    response = await client.get(f"/artists/{phoebe}", headers=headers)
    similar = response.json()["similar"]
    # Japanese Breakfast and The National share "indie rock" with Phoebe Bridgers; Denzel
    # Curry (hip hop, trap, rage rap) is the farthest of the nine seeded peers.
    assert [artist["name"] for artist in similar] == [
        "Japanese Breakfast",
        "Mannequin Pussy",
        "The National",
        "Sylvan Esso",
        "Jason Isbell",
        "Turnstile",
    ]
    ids = {artist["id"] for artist in similar}
    assert phoebe not in ids
    assert unembedded_artist not in ids
    assert similar[0]["genres"] == ["indie pop", "dream pop", "indie rock"]


async def test_similar_artists_carry_follow_state(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """A followed similar artist is flagged as followed for the viewer."""
    headers = await auth_headers(client, "similar-follow@example.com")
    await client.post(
        "/follows",
        json={"artist_id": await seeded_artist_id(db, "Japanese Breakfast")},
        headers=headers,
    )
    response = await client.get(
        f"/artists/{await seeded_artist_id(db, 'Phoebe Bridgers')}", headers=headers
    )
    followed = {artist["name"]: artist["followed"] for artist in response.json()["similar"]}
    assert followed["Japanese Breakfast"] is True
    assert followed["The National"] is False


async def test_similar_is_empty_for_artist_without_embedding(
    client: httpx.AsyncClient, unembedded_artist: str
) -> None:
    """An artist with no embedding has no similar artists."""
    headers = await auth_headers(client, "no-embedding@example.com")
    response = await client.get(f"/artists/{unembedded_artist}", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Unembedded Band"
    assert body["similar"] == []
