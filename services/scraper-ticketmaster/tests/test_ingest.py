"""Integration tests: ingest the fixture into a containerized Postgres with real seeds."""

import copy
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.db import ingest_payload

EXPECTED_VENUE_TM_IDS = {
    "Newport Music Hall": "KovZpZAE6ktA",
    "Ace of Cups": "KovZpZAJ6dlA",
    "The Basement": "KovZpZAEkn1A",
    "KEMBA Live!": "KovZpZAEdFtJ",
    "Nationwide Arena": "KovZpZA7AAEA",
}


async def _scalar(engine: AsyncEngine, sql: str, params: dict[str, Any] | None = None) -> Any:
    """Run a query and return its first scalar value."""
    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params or {})).scalar()


async def _row_counts(engine: AsyncEngine) -> dict[str, int]:
    """Return row counts for the tables the ingest touches."""
    return {
        table: int(await _scalar(engine, f"SELECT count(*) FROM {table}"))
        for table in ("venues", "artists", "events", "event_artists")
    }


async def test_ingest_merges_venues_reuses_artists_and_creates_events(
    db_engine: AsyncEngine, payload: dict[str, Any]
) -> None:
    """One ingest attaches TM ids to seeded venues, reuses seed artists, and lands all rows."""
    stats = await ingest_payload(db_engine, payload)

    assert await _row_counts(db_engine) == {
        "venues": 5,
        "artists": 12,
        "events": 9,
        "event_artists": 10,
    }
    for name, tm_id in EXPECTED_VENUE_TM_IDS.items():
        stored = await _scalar(
            db_engine,
            "SELECT source_ids->>'ticketmaster' FROM venues WHERE name = :name",
            {"name": name},
        )
        assert stored == tm_id, f"venue {name!r} should carry its Ticketmaster id"

    async with db_engine.connect() as conn:
        national = (
            await conn.execute(
                text(
                    "SELECT embedding IS NOT NULL, genres FROM artists WHERE name = 'The National'"
                )
            )
        ).one()
    assert national[0] is True, "seed embedding must not be overwritten"
    assert national[1] == ["indie rock", "chamber pop", "post-punk revival"]

    new_artist_genres = await _scalar(
        db_engine, "SELECT genres FROM artists WHERE name = 'MJ Lenderman'"
    )
    assert new_artist_genres == ["Rock", "Alternative Rock"]

    async with db_engine.connect() as conn:
        event_row = (
            await conn.execute(
                text(
                    "SELECT title, status::text, price_min_cents, price_max_cents, currency"
                    " FROM events WHERE external_id = 'vvG1fZ9K3sNqTm'"
                )
            )
        ).one()
    assert tuple(event_row) == ("The National with MJ Lenderman", "on_sale", 3950, 8950, "USD")
    postponed = await _scalar(
        db_engine, "SELECT status::text FROM events WHERE external_id = 'vvG1fZ9dNb5cXe'"
    )
    assert postponed == "postponed"

    async with db_engine.connect() as conn:
        lineup = (
            await conn.execute(
                text(
                    "SELECT a.name, ea.billing FROM event_artists ea"
                    " JOIN artists a ON a.id = ea.artist_id"
                    " JOIN events e ON e.id = ea.event_id"
                    " WHERE e.external_id = 'vvG1fZ9K3sNqTm' ORDER BY ea.billing"
                )
            )
        ).all()
    assert [tuple(row) for row in lineup] == [("The National", 0), ("MJ Lenderman", 1)]

    assert stats.events_seen == 9
    assert stats.events_new == 9
    assert stats.events_updated == 0
    assert stats.status_changes == 0
    assert stats.venues_created == 0
    assert stats.artists_created == 2


async def test_ingesting_twice_is_idempotent(
    db_engine: AsyncEngine, payload: dict[str, Any]
) -> None:
    """Re-ingesting the same payload changes no row counts and creates nothing."""
    await ingest_payload(db_engine, payload)
    first_counts = await _row_counts(db_engine)

    stats = await ingest_payload(db_engine, payload)

    assert await _row_counts(db_engine) == first_counts
    assert stats.events_new == 0
    assert stats.events_updated == 9
    assert stats.status_changes == 0
    assert stats.venues_created == 0
    assert stats.artists_created == 0


async def test_status_change_is_applied_and_detected(
    db_engine: AsyncEngine, payload: dict[str, Any]
) -> None:
    """A changed status code updates the row and is counted as a status change."""
    await ingest_payload(db_engine, payload)

    mutated = copy.deepcopy(payload)
    for raw in mutated["_embedded"]["events"]:
        if raw["id"] == "vvG1fZ9pTu2rHs":
            raw["dates"]["status"]["code"] = "canceled"
    stats = await ingest_payload(db_engine, mutated)

    stored = await _scalar(
        db_engine, "SELECT status::text FROM events WHERE external_id = 'vvG1fZ9pTu2rHs'"
    )
    assert stored == "cancelled"
    assert stats.status_changes == 1
    assert stats.events_updated == 9
    assert stats.events_new == 0
