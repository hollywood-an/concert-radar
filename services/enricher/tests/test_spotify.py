"""Spotify client tests: disabled mode and the client-credentials flow over a mock."""

import httpx

from src.spotify import SpotifyClient


def _spotify_transport(
    token_requests: list[int], search_requests: list[str]
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "accounts.spotify.com":
            token_requests.append(1)
            return httpx.Response(200, json={"access_token": "tok-1", "expires_in": 3600})
        assert request.headers["Authorization"] == "Bearer tok-1"
        search_requests.append(request.url.params["q"])
        return httpx.Response(
            200,
            json={
                "artists": {
                    "items": [
                        {
                            "id": "sp-123",
                            "name": "Wet Leg",
                            "genres": ["indie rock"],
                            "popularity": 71,
                            "images": [{"url": "https://img.example/wetleg.jpg"}],
                        }
                    ]
                }
            },
        )

    return httpx.MockTransport(handler)


async def test_disabled_without_credentials() -> None:
    """Empty or placeholder credentials disable the client entirely."""
    for client_id in ("", "<your Spotify app client ID>"):
        client = SpotifyClient(client_id, "secret")
        assert client.enabled is False
        assert await client.search_artist("Anyone") is None
        await client.aclose()


async def test_search_returns_metadata_and_caches_token() -> None:
    """Searches return artist metadata and reuse one client-credentials token."""
    token_requests: list[int] = []
    search_requests: list[str] = []
    client = SpotifyClient(
        "real-id", "real-secret", transport=_spotify_transport(token_requests, search_requests)
    )
    try:
        first = await client.search_artist("Wet Leg")
        second = await client.search_artist("Wet Leg")
    finally:
        await client.aclose()

    assert first is not None and second is not None
    assert first.spotify_id == "sp-123"
    assert first.genres == ["indie rock"]
    assert first.popularity == 71
    assert first.image_url == "https://img.example/wetleg.jpg"
    assert search_requests == ["Wet Leg", "Wet Leg"]
    assert len(token_requests) == 1
