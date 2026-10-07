"""Tests for GET /geocode and the Nominatim client over a mock Nominatim."""

import time

import httpx
import pytest

from src.geocode import NominatimClient
from tests.conftest import auth_headers

_COLUMBUS = [
    {
        "display_name": "Columbus, Franklin County, Ohio, United States",
        "lat": "39.9622601",
        "lon": "-83.0007065",
    },
    {
        "display_name": "Columbus, Bartholomew County, Indiana, United States",
        "lat": "39.2014405",
        "lon": "-85.9213796",
    },
]


def _nominatim(requests: list[httpx.Request], status_code: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/search"
        return httpx.Response(status_code, json=_COLUMBUS if status_code == 200 else {})

    return httpx.MockTransport(handler)


@pytest.fixture
def nominatim(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """Swap in a mock-backed geocoder; returns the requests it receives."""
    from src.routes import geocode as geocode_routes

    requests: list[httpx.Request] = []
    client = NominatimClient(
        "https://nominatim.test", transport=_nominatim(requests), min_interval_s=0
    )
    monkeypatch.setattr(geocode_routes, "get_geocoder", lambda: client)
    return requests


async def test_geocode_returns_places(
    client: httpx.AsyncClient, nominatim: list[httpx.Request]
) -> None:
    headers = await auth_headers(client, "geo@example.com")

    response = await client.get("/geocode", params={"q": "Columbus"}, headers=headers)

    assert response.status_code == 200
    assert response.json() == [
        {
            "label": "Columbus, Franklin County, Ohio, United States",
            "lat": 39.9622601,
            "lon": -83.0007065,
        },
        {
            "label": "Columbus, Bartholomew County, Indiana, United States",
            "lat": 39.2014405,
            "lon": -85.9213796,
        },
    ]
    sent = nominatim[0]
    assert sent.url.params["format"] == "jsonv2"
    assert sent.url.params["limit"] == "5"
    assert sent.headers["User-Agent"].startswith("concert-radar/")


async def test_geocode_requires_sign_in(
    client: httpx.AsyncClient, nominatim: list[httpx.Request]
) -> None:
    response = await client.get("/geocode", params={"q": "Columbus"})

    assert response.status_code == 401
    assert nominatim == []


async def test_geocode_rejects_short_queries(
    client: httpx.AsyncClient, nominatim: list[httpx.Request]
) -> None:
    headers = await auth_headers(client, "geo@example.com")

    response = await client.get("/geocode", params={"q": "Co"}, headers=headers)

    assert response.status_code == 422
    assert nominatim == []


async def test_geocode_answers_503_when_nominatim_fails(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.routes import geocode as geocode_routes

    failing = NominatimClient(
        "https://nominatim.test", transport=_nominatim([], status_code=500), min_interval_s=0
    )
    monkeypatch.setattr(geocode_routes, "get_geocoder", lambda: failing)
    headers = await auth_headers(client, "geo@example.com")

    response = await client.get("/geocode", params={"q": "Columbus"}, headers=headers)

    assert response.status_code == 503


async def test_repeat_queries_are_served_from_cache() -> None:
    requests: list[httpx.Request] = []
    geocoder = NominatimClient(
        "https://nominatim.test", transport=_nominatim(requests), min_interval_s=0
    )

    first = await geocoder.search("Columbus, OH")
    second = await geocoder.search("  columbus,   oh ")

    assert second == first
    assert len(requests) == 1
    await geocoder.aclose()


async def test_requests_are_spaced_by_the_minimum_interval() -> None:
    requests: list[httpx.Request] = []
    geocoder = NominatimClient(
        "https://nominatim.test", transport=_nominatim(requests), min_interval_s=0.3
    )

    started = time.monotonic()
    await geocoder.search("Columbus")
    await geocoder.search("Cleveland")
    elapsed = time.monotonic() - started

    assert len(requests) == 2
    assert elapsed >= 0.3
    await geocoder.aclose()
