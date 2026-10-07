"""Address search through OpenStreetMap's Nominatim, for setting a home location.

Nominatim's usage policy asks for an identifying User-Agent, at most one request per
second, cached results, and no search-as-you-type. The web app searches only on submit;
this client identifies itself, spaces requests at least a second apart across the whole
process, and keeps recent answers in memory.
"""

import asyncio
import math
import time
from collections import OrderedDict
from functools import lru_cache

import httpx

from src.config import get_settings
from src.schemas import GeocodeResult

_USER_AGENT = "concert-radar/1.0 (+https://github.com/hollywood-an/concert-radar)"
_RESULT_LIMIT = 5
_CACHE_SIZE = 256


class GeocoderUnavailable(Exception):
    """Nominatim errored or timed out."""


class NominatimClient:
    """Rate-limited, cached Nominatim search."""

    def __init__(
        self,
        base_url: str,
        transport: httpx.AsyncBaseTransport | None = None,
        min_interval_s: float = 1.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            transport=transport, timeout=10.0, headers={"User-Agent": _USER_AGENT}
        )
        self._min_interval_s = min_interval_s
        self._lock = asyncio.Lock()
        self._last_request = -math.inf
        self._cache: OrderedDict[str, list[GeocodeResult]] = OrderedDict()

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def search(self, query: str) -> list[GeocodeResult]:
        """Return up to five places matching a free-form address or place name."""
        key = " ".join(query.lower().split())
        if (cached := self._cached(key)) is not None:
            return cached
        async with self._lock:
            # Another request may have fetched this query while we waited for the lock.
            if (cached := self._cached(key)) is not None:
                return cached
            wait = self._last_request + self._min_interval_s - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                response = await self._client.get(
                    f"{self._base_url}/search",
                    params={"q": key, "format": "jsonv2", "limit": _RESULT_LIMIT},
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise GeocoderUnavailable(str(exc)) from exc
            finally:
                self._last_request = time.monotonic()
        results = [
            GeocodeResult(
                label=str(item["display_name"]), lat=float(item["lat"]), lon=float(item["lon"])
            )
            for item in response.json()
        ]
        self._cache[key] = results
        if len(self._cache) > _CACHE_SIZE:
            self._cache.popitem(last=False)
        return results

    def _cached(self, key: str) -> list[GeocodeResult] | None:
        results = self._cache.get(key)
        if results is not None:
            self._cache.move_to_end(key)
        return results


@lru_cache
def get_geocoder() -> NominatimClient:
    """Return the process-wide Nominatim client built from settings."""
    return NominatimClient(get_settings().nominatim_url)
