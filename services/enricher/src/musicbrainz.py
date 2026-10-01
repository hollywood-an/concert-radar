"""MusicBrainz artist lookup honoring the required 1 request/second rate limit."""

import asyncio

import httpx
import structlog
from pydantic import BaseModel

log = structlog.get_logger()

_BASE_URL = "https://musicbrainz.org/ws/2"
# MusicBrainz requires a contactable User-Agent and one request per second per client.
_USER_AGENT = "ConcertRadar/0.1 (https://github.com/hollywood-an/concert-radar)"
_MAX_TAGS = 6
MAX_ATTEMPTS = 4


class MBArtist(BaseModel):
    """The accepted top search result for an artist name."""

    mbid: str
    name: str
    score: int
    tags: list[str]


class MusicBrainzClient:
    """Throttled search client over the MusicBrainz /ws/2 API."""

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport | None = None,
        min_interval: float = 1.0,
        retry_delay: float = 1.0,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={"User-Agent": _USER_AGENT},
            transport=transport,
            timeout=15.0,
        )
        self._min_interval = min_interval
        self._retry_delay = retry_delay
        self._lock = asyncio.Lock()
        self._last_request = 0.0

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def _throttle(self) -> None:
        """Sleep as needed so requests are at least min_interval seconds apart."""
        async with self._lock:
            loop = asyncio.get_running_loop()
            wait = self._last_request + self._min_interval - loop.time()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = loop.time()

    async def _search(self, params: dict[str, str | int]) -> httpx.Response:
        """GET /artist, retrying with exponential backoff while MusicBrainz answers 503."""
        # MusicBrainz answers 503 both when it is overloaded and when a client exceeds the
        # rate limit; both clear within seconds, so one 503 must not crash the consumer.
        delay = self._retry_delay
        for attempt in range(1, MAX_ATTEMPTS + 1):
            await self._throttle()
            response = await self._client.get("/artist", params=params)
            if response.status_code != httpx.codes.SERVICE_UNAVAILABLE or attempt == MAX_ATTEMPTS:
                response.raise_for_status()
                return response
            log.warning("musicbrainz unavailable, retrying", attempt=attempt, delay=delay)
            await asyncio.sleep(delay)
            delay *= 2
        raise AssertionError("unreachable: retry loop always returns or raises")

    async def search_artist(self, name: str) -> MBArtist | None:
        """Return the top search result when its score exceeds 70, else None."""
        escaped = name.replace('"', '\\"')
        response = await self._search({"query": f'artist:"{escaped}"', "fmt": "json", "limit": 5})
        artists = response.json().get("artists") or []
        if not artists:
            log.info("musicbrainz: no results", artist=name)
            return None
        top = artists[0]
        score = int(top.get("score") or 0)
        if score <= 70:
            log.info("musicbrainz: top score too low", artist=name, score=score)
            return None
        tags = sorted(
            (t for t in top.get("tags") or [] if t.get("name")),
            key=lambda t: -int(t.get("count") or 0),
        )
        return MBArtist(
            mbid=str(top["id"]),
            name=str(top.get("name") or name),
            score=score,
            tags=[str(t["name"]) for t in tags[:_MAX_TAGS]],
        )
