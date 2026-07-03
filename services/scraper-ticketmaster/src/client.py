"""Async httpx client for the Ticketmaster Discovery API v2."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx
import structlog

log = structlog.get_logger()

BASE_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
PAGE_SIZE = 200
MAX_PAGES = 5
MAX_ATTEMPTS = 3


class DiscoveryClient:
    """Paginating client for the Discovery API music-events listing."""

    def __init__(
        self,
        api_key: str,
        dma_id: int,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_delay: float = 1.0,
    ) -> None:
        """Store the API key, DMA to scrape, and optional transport/backoff overrides."""
        self._api_key = api_key
        self._dma_id = dma_id
        self._transport = transport
        self._retry_delay = retry_delay

    async def fetch_pages(self) -> AsyncIterator[dict[str, Any]]:
        """Yield event pages until totalPages or the page cap is exhausted."""
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0), transport=self._transport
        ) as http:
            page = 0
            total_pages = 1
            while page < min(total_pages, MAX_PAGES):
                response = await self._get_page(http, page)
                payload: dict[str, Any] = response.json()
                total_pages = int((payload.get("page") or {}).get("totalPages") or 1)
                yield payload
                page += 1

    async def _get_page(self, http: httpx.AsyncClient, page: int) -> httpx.Response:
        """Fetch one page, retrying with exponential backoff on 429 rate-limit responses."""
        params = {
            "apikey": self._api_key,
            "classificationName": "music",
            "dmaId": str(self._dma_id),
            "size": str(PAGE_SIZE),
            "page": str(page),
        }
        delay = self._retry_delay
        for attempt in range(1, MAX_ATTEMPTS + 1):
            response = await http.get(BASE_URL, params=params)
            if response.status_code != httpx.codes.TOO_MANY_REQUESTS or attempt == MAX_ATTEMPTS:
                response.raise_for_status()
                return response
            log.warning("rate limited by Discovery API", page=page, attempt=attempt)
            await asyncio.sleep(delay)
            delay *= 2
        raise AssertionError("unreachable: retry loop always returns or raises")
