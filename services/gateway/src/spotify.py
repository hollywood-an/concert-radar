"""Spotify OAuth (authorization-code flow) and followed-artist import client.

Inert without credentials: `enabled` is False and the auth routes answer 503, so the
rest of the gateway works keyless.
"""

from functools import lru_cache
from typing import Any
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel

from src.config import get_settings

_ACCOUNTS_BASE = "https://accounts.spotify.com"
_API_BASE = "https://api.spotify.com/v1"
_SCOPES = "user-read-email user-follow-read"


class SpotifyProfile(BaseModel):
    """The authenticated Spotify user's identity."""

    spotify_id: str
    email: str
    display_name: str | None


class SpotifyFollowedArtist(BaseModel):
    """One artist the Spotify user follows."""

    spotify_id: str
    name: str
    genres: list[str]
    popularity: int | None
    image_url: str | None


class SpotifyOAuthClient:
    """Authorization-code OAuth plus the follow-list fetch used by the import."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._client = httpx.AsyncClient(transport=transport, timeout=15.0)

    @property
    def enabled(self) -> bool:
        """Whether real credentials are configured (env placeholders do not count)."""
        return bool(self._client_id and self._client_secret and not self._client_id.startswith("<"))

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    def authorize_url(self, state: str) -> str:
        """Build the Spotify authorize redirect for this app."""
        query = urlencode(
            {
                "client_id": self._client_id,
                "response_type": "code",
                "redirect_uri": self._redirect_uri,
                "scope": _SCOPES,
                "state": state,
            }
        )
        return f"{_ACCOUNTS_BASE}/authorize?{query}"

    async def exchange_code(self, code: str) -> tuple[str, str | None]:
        """Trade an authorization code for (access_token, refresh_token)."""
        response = await self._client.post(
            f"{_ACCOUNTS_BASE}/api/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self._redirect_uri,
            },
            auth=(self._client_id, self._client_secret),
        )
        response.raise_for_status()
        body = response.json()
        return str(body["access_token"]), body.get("refresh_token")

    async def get_profile(self, access_token: str) -> SpotifyProfile:
        """Fetch the authenticated user's Spotify profile."""
        response = await self._client.get(
            f"{_API_BASE}/me", headers={"Authorization": f"Bearer {access_token}"}
        )
        response.raise_for_status()
        body = response.json()
        return SpotifyProfile(
            spotify_id=str(body["id"]),
            email=str(body["email"]),
            display_name=body.get("display_name"),
        )

    async def get_followed_artists(self, access_token: str) -> list[SpotifyFollowedArtist]:
        """Fetch every artist the user follows, walking the cursor pagination."""
        artists: list[SpotifyFollowedArtist] = []
        after: str | None = None
        while True:
            params: dict[str, Any] = {"type": "artist", "limit": 50}
            if after is not None:
                params["after"] = after
            response = await self._client.get(
                f"{_API_BASE}/me/following",
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            page = response.json()["artists"]
            for item in page.get("items") or []:
                images = item.get("images") or []
                artists.append(
                    SpotifyFollowedArtist(
                        spotify_id=str(item["id"]),
                        name=str(item["name"]),
                        genres=[str(g) for g in item.get("genres") or []],
                        popularity=item.get("popularity"),
                        image_url=str(images[0]["url"]) if images else None,
                    )
                )
            after = (page.get("cursors") or {}).get("after")
            if not after or not page.get("items"):
                return artists


@lru_cache
def get_spotify_oauth() -> SpotifyOAuthClient:
    """Return the process-wide Spotify OAuth client built from settings."""
    settings = get_settings()
    return SpotifyOAuthClient(
        settings.spotify_client_id,
        settings.spotify_client_secret,
        settings.spotify_redirect_uri,
    )
