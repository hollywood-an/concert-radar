"""MusicBrainz client tests over a mock transport."""

import asyncio

from src.musicbrainz import MusicBrainzClient
from tests.conftest import mb_artist_json, mb_transport


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
