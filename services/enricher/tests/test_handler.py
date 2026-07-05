"""Handler tests: enrichment outcomes are observable as Postgres state."""

import math
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.embeddings import embed_genres
from src.handler import process_deduped
from src.musicbrainz import MusicBrainzClient
from src.spotify import SpotifyClient
from tests.conftest import (
    create_artist,
    create_event,
    make_deduped,
    mb_artist_json,
    mb_transport,
    parse_vector,
)


def _disabled_spotify() -> SpotifyClient:
    return SpotifyClient("", "")


async def _artist_row(engine: AsyncEngine, artist_id: UUID) -> Any:
    async with engine.connect() as conn:
        return (
            await conn.execute(
                text(
                    "SELECT name, mbid, genres, embedding::text AS embedding"
                    " FROM artists WHERE id = :id"
                ),
                {"id": artist_id},
            )
        ).first()


async def test_stub_artist_gains_mbid_genres_and_embedding(db_engine: AsyncEngine) -> None:
    """A bare scraped artist is resolved against MusicBrainz and embedded."""
    artist_id = await create_artist(db_engine, "Wet Leg", genres=["Rock"])
    event_id, venue_id = await create_event(db_engine, [artist_id])
    mb = MusicBrainzClient(
        transport=mb_transport(
            {
                "Wet Leg": mb_artist_json(
                    "mb-wetleg", "Wet Leg", tags=(("indie rock", 9), ("post-punk", 3))
                )
            }
        ),
        min_interval=0.0,
    )
    try:
        result = await process_deduped(
            db_engine, mb, _disabled_spotify(), make_deduped(event_id, venue_id, [artist_id])
        )
    finally:
        await mb.aclose()

    assert result.artist_ids == [artist_id]
    assert result.enriched_artist_ids == [artist_id]
    row = await _artist_row(db_engine, artist_id)
    assert row.mbid == "mb-wetleg"
    assert row.genres == ["indie rock", "post-punk"]
    assert row.embedding is not None
    fresh = embed_genres(["indie rock", "post-punk"])
    assert fresh is not None
    # The column is float4 and the literal is written at 6 decimals, so compare loosely.
    assert parse_vector(row.embedding) == pytest.approx(fresh, abs=1e-5)


async def test_second_pass_skips_network(db_engine: AsyncEngine) -> None:
    """An already-enriched artist is not looked up again on later events."""
    artist_id = await create_artist(db_engine, "Wet Leg")
    event_id, venue_id = await create_event(db_engine, [artist_id])
    calls: list[str] = []
    mb = MusicBrainzClient(
        transport=mb_transport({"Wet Leg": mb_artist_json("mb-wetleg", "Wet Leg")}, calls),
        min_interval=0.0,
    )
    deduped = make_deduped(event_id, venue_id, [artist_id])
    try:
        first = await process_deduped(db_engine, mb, _disabled_spotify(), deduped)
        second = await process_deduped(db_engine, mb, _disabled_spotify(), deduped)
    finally:
        await mb.aclose()

    assert first.enriched_artist_ids == [artist_id]
    assert second.enriched_artist_ids == []
    assert calls == ["Wet Leg"]


async def test_mbid_collision_merges_stub_into_canonical(db_engine: AsyncEngine) -> None:
    """A duplicate spelling resolving to an existing mbid is merged into that row."""
    async with db_engine.begin() as conn:
        canonical_id = (
            await conn.execute(
                text(
                    "UPDATE artists SET mbid = 'mb-phoebe' WHERE name = 'Phoebe Bridgers'"
                    " RETURNING id"
                )
            )
        ).scalar_one()
        user_id = (
            await conn.execute(
                text("INSERT INTO users (email) VALUES ('merge@example.com') RETURNING id")
            )
        ).scalar_one()

    stub_id = await create_artist(db_engine, "Phoebe  Bridgers")
    event_id, venue_id = await create_event(db_engine, [stub_id])
    async with db_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO follows (user_id, artist_id) VALUES (:u, :a)"),
            {"u": user_id, "a": stub_id},
        )

    mb = MusicBrainzClient(
        transport=mb_transport(
            {"Phoebe  Bridgers": mb_artist_json("mb-phoebe", "Phoebe Bridgers")}
        ),
        min_interval=0.0,
    )
    try:
        result = await process_deduped(
            db_engine, mb, _disabled_spotify(), make_deduped(event_id, venue_id, [stub_id])
        )
    finally:
        await mb.aclose()

    assert result.artist_ids == [canonical_id]
    async with db_engine.connect() as conn:
        assert (
            await conn.execute(text("SELECT count(*) FROM artists WHERE id = :id"), {"id": stub_id})
        ).scalar_one() == 0
        lineup_artist = (
            await conn.execute(
                text("SELECT artist_id FROM event_artists WHERE event_id = :id"),
                {"id": event_id},
            )
        ).scalar_one()
        followed_artist = (
            await conn.execute(
                text("SELECT artist_id FROM follows WHERE user_id = :id"), {"id": user_id}
            )
        ).scalar_one()
    assert lineup_artist == canonical_id
    assert followed_artist == canonical_id


async def test_no_mb_match_embeds_scraper_genres(db_engine: AsyncEngine) -> None:
    """Without a MusicBrainz match, the scraper's genres still produce an embedding."""
    artist_id = await create_artist(db_engine, "Local Opener", genres=["Rock", "Alternative"])
    event_id, venue_id = await create_event(db_engine, [artist_id])
    mb = MusicBrainzClient(transport=mb_transport({}), min_interval=0.0)
    try:
        await process_deduped(
            db_engine, mb, _disabled_spotify(), make_deduped(event_id, venue_id, [artist_id])
        )
    finally:
        await mb.aclose()

    row = await _artist_row(db_engine, artist_id)
    assert row.mbid is None
    assert row.genres == ["Rock", "Alternative"]
    assert row.embedding is not None


async def test_no_match_and_no_genres_leaves_no_embedding(db_engine: AsyncEngine) -> None:
    """With nothing to embed, the artist keeps a NULL embedding (0.5 feed fallback)."""
    artist_id = await create_artist(db_engine, "Total Mystery")
    event_id, venue_id = await create_event(db_engine, [artist_id])
    mb = MusicBrainzClient(transport=mb_transport({}), min_interval=0.0)
    try:
        result = await process_deduped(
            db_engine, mb, _disabled_spotify(), make_deduped(event_id, venue_id, [artist_id])
        )
    finally:
        await mb.aclose()

    assert result.enriched_artist_ids == [artist_id]
    row = await _artist_row(db_engine, artist_id)
    assert row.mbid is None
    assert row.embedding is None


async def test_missing_artist_row_is_skipped(db_engine: AsyncEngine) -> None:
    """A deduped payload naming a vanished artist id is handled without error."""
    artist_id = await create_artist(db_engine, "Wet Leg")
    event_id, venue_id = await create_event(db_engine, [artist_id])
    mb = MusicBrainzClient(transport=mb_transport({}), min_interval=0.0)
    try:
        result = await process_deduped(
            db_engine, mb, _disabled_spotify(), make_deduped(event_id, venue_id, [uuid4()])
        )
    finally:
        await mb.aclose()
    assert result.artist_ids == []
    assert result.enriched_artist_ids == []


async def test_live_embedding_matches_seed_vector_space(db_engine: AsyncEngine) -> None:
    """Embedding a seeded artist's genres reproduces its seeded vector (same model+format)."""
    async with db_engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT genres, embedding::text AS embedding FROM artists"
                    " WHERE name = 'Phoebe Bridgers'"
                )
            )
        ).one()
    seeded = parse_vector(row.embedding)
    live = embed_genres(list(row.genres))
    assert live is not None

    dot = sum(a * b for a, b in zip(seeded, live, strict=True))
    norm = math.sqrt(sum(a * a for a in seeded)) * math.sqrt(sum(b * b for b in live))
    assert dot / norm > 0.999
