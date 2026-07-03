"""Unit tests for Discovery API pagination and rate-limit behavior via httpx.MockTransport."""

import json
from typing import Any

import httpx
import pytest

from src.client import BASE_URL, MAX_PAGES, PAGE_SIZE, DiscoveryClient


def _page_payload(page_number: int, total_pages: int) -> dict[str, Any]:
    """Build a minimal Discovery API page payload."""
    return {
        "_embedded": {"events": [{"id": f"ev-{page_number}"}]},
        "page": {"number": page_number, "totalPages": total_pages},
    }


def _transport(responses: list[httpx.Response], seen: list[httpx.Request]) -> httpx.MockTransport:
    """Return a MockTransport that records requests and replays canned responses."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return responses[len(seen) - 1]

    return httpx.MockTransport(handler)


async def _collect(client: DiscoveryClient) -> list[dict[str, Any]]:
    """Drain fetch_pages into a list."""
    return [page async for page in client.fetch_pages()]


async def test_paginates_until_total_pages_and_sends_expected_params() -> None:
    """Three total pages produce three requests with correct query params and page numbers."""
    seen: list[httpx.Request] = []
    responses = [httpx.Response(200, text=json.dumps(_page_payload(n, 3))) for n in range(3)]
    client = DiscoveryClient("test-key", 249, transport=_transport(responses, seen))

    pages = await _collect(client)

    assert [p["page"]["number"] for p in pages] == [0, 1, 2]
    assert len(seen) == 3
    for page_number, request in enumerate(seen):
        assert request.url.copy_with(query=None) == httpx.URL(BASE_URL)
        params = dict(httpx.QueryParams(request.url.query))
        assert params == {
            "apikey": "test-key",
            "classificationName": "music",
            "dmaId": "249",
            "size": str(PAGE_SIZE),
            "page": str(page_number),
        }


async def test_stops_at_page_cap_when_total_pages_exceeds_it() -> None:
    """Ten total pages stop at MAX_PAGES requests."""
    seen: list[httpx.Request] = []
    responses = [
        httpx.Response(200, text=json.dumps(_page_payload(n, 10))) for n in range(MAX_PAGES)
    ]
    client = DiscoveryClient("test-key", 249, transport=_transport(responses, seen))

    pages = await _collect(client)

    assert len(pages) == MAX_PAGES
    assert len(seen) == MAX_PAGES


async def test_retries_rate_limited_page_then_succeeds() -> None:
    """A 429 response is retried and the page is eventually yielded."""
    seen: list[httpx.Request] = []
    responses = [
        httpx.Response(429, text="rate limited"),
        httpx.Response(200, text=json.dumps(_page_payload(0, 1))),
    ]
    client = DiscoveryClient(
        "test-key", 249, transport=_transport(responses, seen), retry_delay=0.01
    )

    pages = await _collect(client)

    assert len(pages) == 1
    assert len(seen) == 2


async def test_persistent_rate_limiting_raises() -> None:
    """429 on every attempt surfaces an HTTPStatusError after the retry budget."""
    seen: list[httpx.Request] = []
    responses = [httpx.Response(429, text="rate limited") for _ in range(3)]
    client = DiscoveryClient(
        "test-key", 249, transport=_transport(responses, seen), retry_delay=0.01
    )

    with pytest.raises(httpx.HTTPStatusError):
        await _collect(client)
    assert len(seen) == 3
