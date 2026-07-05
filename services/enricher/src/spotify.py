"""Optional Spotify artist metadata via the client-credentials flow.

The client is disabled (every lookup returns None) when credentials are not configured,
so enrichment works keyless with MusicBrainz alone.
"""

import asyncio
import time

import httpx
import structlog
from pydantic import BaseModel

log = structlog.get_logger()

_ACCOUNTS_URL = "https://accounts.spotify.com/api/token"
_API_BASE_URL = "https://api.spotify.com/v1"


class SpotifyArtist(BaseModel):
    """Metadata for the best-matching Spotify artist."""

    spotify_id: str
    genres: list[str]
    popularity: int | None
    image_url: str | None


class SpotifyClient:
    """Search client over the Spotify Web API; inert without credentials."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._client = httpx.AsyncClient(transport=transport, timeout=15.0)
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        """Whether real credentials are configured (env placeholders do not count)."""
        return bool(self._client_id and self._client_secret and not self._client_id.startswith("<"))

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def _get_token(self) -> str:
        """Return a cached client-credentials token, refreshing when expired."""
        async with self._lock:
            if self._token is not None and time.monotonic() < self._token_expires_at:
                return self._token
            response = await self._client.post(
                _ACCOUNTS_URL,
                data={"grant_type": "client_credentials"},
                auth=(self._client_id, self._client_secret),
            )
            response.raise_for_status()
            body = response.json()
            self._token = str(body["access_token"])
            self._token_expires_at = time.monotonic() + int(body.get("expires_in", 3600)) - 60
            return self._token

    async def search_artist(self, name: str) -> SpotifyArtist | None:
        """Return metadata for the top artist search hit; None when disabled or not found."""
        if not self.enabled:
            return None
        try:
            token = await self._get_token()
            response = await self._client.get(
                f"{_API_BASE_URL}/search",
                params={"q": name, "type": "artist", "limit": 1},
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            items = response.json().get("artists", {}).get("items") or []
        except httpx.HTTPError:
            log.warning("spotify lookup failed", artist=name, exc_info=True)
            return None
        if not items:
            return None
        item = items[0]
        images = item.get("images") or []
        return SpotifyArtist(
            spotify_id=str(item["id"]),
            genres=[str(g) for g in item.get("genres") or []],
            popularity=item.get("popularity"),
            image_url=str(images[0]["url"]) if images else None,
        )
