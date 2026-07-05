"""Tests for the Spotify OAuth + import flow over a mock Spotify."""

import json

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.spotify import SpotifyOAuthClient
from tests.conftest import auth_headers

_FOLLOWED = [
    {
        "id": "sp-phoebe",
        "name": "Phoebe Bridgers",
        "genres": ["indie folk"],
        "popularity": 75,
        "images": [{"url": "https://img.example/pb.jpg"}],
    },
    {
        "id": "sp-wetleg",
        "name": "Wet Leg",
        "genres": ["indie rock", "post-punk"],
        "popularity": 70,
        "images": [{"url": "https://img.example/wl.jpg"}],
    },
    {
        "id": "sp-mystery",
        "name": "Import Mystery",
        "genres": [],
        "popularity": None,
        "images": [],
    },
]


def _spotify_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "accounts.spotify.com" and request.url.path == "/api/token":
            body = dict(pair.split("=", 1) for pair in request.content.decode().split("&"))
            assert body["grant_type"] == "authorization_code"
            assert body["code"] == "test-code"
            return httpx.Response(
                200, json={"access_token": "sp-access", "refresh_token": "sp-refresh"}
            )
        assert request.headers["Authorization"] == "Bearer sp-access"
        if request.url.path == "/v1/me":
            return httpx.Response(
                200,
                json={
                    "id": "sp-user-1",
                    "email": "spotify-user@example.com",
                    "display_name": "Spotify User",
                },
            )
        if request.url.path == "/v1/me/following":
            return httpx.Response(
                200, json={"artists": {"items": _FOLLOWED, "cursors": {"after": None}}}
            )
        raise AssertionError(f"unexpected request: {request.url}")

    return httpx.MockTransport(handler)


@pytest.fixture
def spotify_enabled(monkeypatch: pytest.MonkeyPatch) -> SpotifyOAuthClient:
    """Configure fake Spotify credentials and swap in a mock-backed OAuth client."""
    from src.routes import auth as auth_routes

    client = SpotifyOAuthClient(
        "test-client-id",
        "test-client-secret",
        "http://localhost:3000/api/auth/spotify/callback",
        transport=_spotify_transport(),
    )
    monkeypatch.setattr(auth_routes, "get_spotify_oauth", lambda: client)
    return client


async def test_spotify_login_unconfigured_returns_503(client: httpx.AsyncClient) -> None:
    """Without credentials the OAuth entrypoint answers 503."""
    response = await client.post("/auth/spotify")
    assert response.status_code == 503


async def test_spotify_login_returns_authorize_url(
    client: httpx.AsyncClient, spotify_enabled: SpotifyOAuthClient
) -> None:
    """With credentials the entrypoint returns the Spotify authorize redirect."""
    headers = await auth_headers(client, "linker@example.com")
    response = await client.post("/auth/spotify", headers=headers)
    assert response.status_code == 200
    url = response.json()["authorize_url"]
    assert url.startswith("https://accounts.spotify.com/authorize?")
    assert "client_id=test-client-id" in url
    assert "user-follow-read" in url
    assert "state=" in url


async def test_callback_links_account_and_imports_follows(
    client: httpx.AsyncClient, db: AsyncSession, spotify_enabled: SpotifyOAuthClient
) -> None:
    """The callback stores tokens, imports follows, sets taste, and returns a session."""
    headers = await auth_headers(client, "importer@example.com")
    authorize_url = (await client.post("/auth/spotify", headers=headers)).json()["authorize_url"]
    state = dict(pair.split("=", 1) for pair in authorize_url.split("?", 1)[1].split("&"))["state"]

    response = await client.get(
        "/auth/spotify/callback", params={"code": "test-code", "state": state}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["imported_artists"] == 3
    assert body["user"]["email"] == "importer@example.com"

    me = await client.get("/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200

    row = (
        (
            await db.execute(
                text(
                    "SELECT spotify_id, spotify_access_token, spotify_refresh_token,"
                    " taste_embedding IS NOT NULL AS has_taste"
                    " FROM users WHERE email = 'importer@example.com'"
                )
            )
        )
        .mappings()
        .one()
    )
    assert row["spotify_id"] == "sp-user-1"
    assert row["spotify_access_token"] == "sp-access"
    assert row["spotify_refresh_token"] == "sp-refresh"
    assert row["has_taste"] is True  # Phoebe Bridgers is seeded with an embedding

    follows = (
        (
            await db.execute(
                text(
                    "SELECT a.name, f.source::text AS source FROM follows f"
                    " JOIN artists a ON a.id = f.artist_id"
                    " JOIN users u ON u.id = f.user_id"
                    " WHERE u.email = 'importer@example.com' ORDER BY a.name"
                )
            )
        )
        .mappings()
        .all()
    )
    assert [f["name"] for f in follows] == ["Import Mystery", "Phoebe Bridgers", "Wet Leg"]
    assert {f["source"] for f in follows} == {"spotify_import"}

    seeded_phoebe = (
        await db.execute(text("SELECT count(*) FROM artists WHERE lower(name) = 'phoebe bridgers'"))
    ).scalar_one()
    assert seeded_phoebe == 1  # reused the seeded row, no duplicate


async def test_callback_import_is_idempotent(
    client: httpx.AsyncClient, db: AsyncSession, spotify_enabled: SpotifyOAuthClient
) -> None:
    """Running the callback twice does not duplicate follows or artists."""
    headers = await auth_headers(client, "again@example.com")
    for _ in range(2):
        authorize_url = (await client.post("/auth/spotify", headers=headers)).json()[
            "authorize_url"
        ]
        state = dict(pair.split("=", 1) for pair in authorize_url.split("?", 1)[1].split("&"))[
            "state"
        ]
        response = await client.get(
            "/auth/spotify/callback", params={"code": "test-code", "state": state}
        )
        assert response.status_code == 200

    count = (
        await db.execute(
            text(
                "SELECT count(*) FROM follows f JOIN users u ON u.id = f.user_id"
                " WHERE u.email = 'again@example.com'"
            )
        )
    ).scalar_one()
    assert count == 3
    wetlegs = (
        await db.execute(text("SELECT count(*) FROM artists WHERE name = 'Wet Leg'"))
    ).scalar_one()
    assert wetlegs == 1


async def test_callback_rejects_bad_state(
    client: httpx.AsyncClient, spotify_enabled: SpotifyOAuthClient
) -> None:
    """A forged or expired state token is rejected with 400."""
    response = await client.get(
        "/auth/spotify/callback", params={"code": "test-code", "state": "forged"}
    )
    assert response.status_code == 400


async def test_taste_updated_published_after_import(
    client: httpx.AsyncClient,
    spotify_enabled: SpotifyOAuthClient,
    kafka_bootstrap: str,
) -> None:
    """The import publishes users.taste_updated for the importing user."""
    from aiokafka import AIOKafkaConsumer

    from src.kafka import USERS_TASTE_UPDATED_TOPIC

    headers = await auth_headers(client, "kafka-import@example.com")
    login = await client.post("/auth/dev", json={"email": "kafka-import@example.com"})
    user_id = login.json()["user"]["id"]
    authorize_url = (await client.post("/auth/spotify", headers=headers)).json()["authorize_url"]
    state = dict(pair.split("=", 1) for pair in authorize_url.split("?", 1)[1].split("&"))["state"]
    await client.get("/auth/spotify/callback", params={"code": "test-code", "state": state})

    consumer = AIOKafkaConsumer(
        USERS_TASTE_UPDATED_TOPIC,
        bootstrap_servers=kafka_bootstrap,
        auto_offset_reset="earliest",
        consumer_timeout_ms=10_000,
    )
    await consumer.start()
    found = False
    try:
        async for message in consumer:
            if message.key == user_id.encode():
                found = True
                assert json.loads(message.value) == {"user_id": user_id}
                break
    finally:
        await consumer.stop()
    assert found
