"""MusicBrainz client tests over a mock transport."""

import asyncio

import httpx
import pytest

from src.musicbrainz import MAX_ATTEMPTS, MusicBrainzClient
from tests.conftest import mb_artist_json, mb_transport


def _status_sequence_transport(
    statuses: list[int], seen: list[httpx.Request]
) -> httpx.MockTransport:
    """Answer each request with the next status; a 200 carries a Wet Leg match."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        status = statuses[len(seen) - 1]
        body = mb_artist_json("mb-wetleg", "Wet Leg") if status == 200 else {"error": "busy"}
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


async def test_accepts_top_result_above_threshold() -> None:
    """A top result scoring above 70 is returned with tags ordered by count."""
    transport = mb_transport(
        {
            "Wet Leg": mb_artist_json(
                "mb-wetleg", "Wet Leg", score=98, tags=(("post-punk", 3), ("indie rock", 9))
            )
        }
    )
    client = MusicBrainzClient(transport=transport, min_interval=0.0)
    try:
        artist = await client.search_artist("Wet Leg")
    finally:
        await client.aclose()
    assert artist is not None
    assert artist.mbid == "mb-wetleg"
    assert artist.score == 98
    assert artist.tags == ["indie rock", "post-punk"]


async def test_rejects_low_score() -> None:
    """A top result scoring 70 or below is rejected per the spec threshold."""
    transport = mb_transport({"Obscure Act": mb_artist_json("mb-x", "Obscure Act", score=70)})
    client = MusicBrainzClient(transport=transport, min_interval=0.0)
    try:
        assert await client.search_artist("Obscure Act") is None
    finally:
        await client.aclose()


async def test_no_results_returns_none() -> None:
    """An empty result set resolves to None."""
    client = MusicBrainzClient(transport=mb_transport({}), min_interval=0.0)
    try:
        assert await client.search_artist("Nobody At All") is None
    finally:
        await client.aclose()


async def test_rate_limit_spaces_requests() -> None:
    """Two consecutive searches are separated by at least min_interval."""
    transport = mb_transport({})
    client = MusicBrainzClient(transport=transport, min_interval=0.3)
    loop = asyncio.get_running_loop()
    try:
        started = loop.time()
        await client.search_artist("First")
        await client.search_artist("Second")
        elapsed = loop.time() - started
    finally:
        await client.aclose()
    assert elapsed >= 0.3


async def test_retries_unavailable_then_succeeds() -> None:
    """503s (MusicBrainz overloaded or rate limiting) are retried until the lookup succeeds."""
    seen: list[httpx.Request] = []
    client = MusicBrainzClient(
        transport=_status_sequence_transport([503, 503, 200], seen),
        min_interval=0.0,
        retry_delay=0.01,
    )
    try:
        artist = await client.search_artist("Wet Leg")
    finally:
        await client.aclose()
    assert artist is not None
    assert artist.mbid == "mb-wetleg"
    assert len(seen) == 3


async def test_persistent_unavailability_raises() -> None:
    """503 on every attempt surfaces an HTTPStatusError after the retry budget."""
    seen: list[httpx.Request] = []
    client = MusicBrainzClient(
        transport=_status_sequence_transport([503] * MAX_ATTEMPTS, seen),
        min_interval=0.0,
        retry_delay=0.01,
    )
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client.search_artist("Wet Leg")
    finally:
        await client.aclose()
    assert len(seen) == MAX_ATTEMPTS


async def test_other_errors_are_not_retried() -> None:
    """A non-503 error fails on the first attempt."""
    seen: list[httpx.Request] = []
    client = MusicBrainzClient(
        transport=_status_sequence_transport([400], seen), min_interval=0.0, retry_delay=0.01
    )
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client.search_artist("Wet Leg")
    finally:
        await client.aclose()
    assert len(seen) == 1
