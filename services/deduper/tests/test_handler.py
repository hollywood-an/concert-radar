"""Handler tests: dedup outcomes are observable as Postgres state."""

from datetime import timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from src.handler import process_discovered
from tests.conftest import STARTS_AT, make_discovered


async def _one(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params)).one()


async def _scalar(engine: AsyncEngine, sql: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        return (await conn.execute(text(sql), params)).scalar_one()


async def test_new_event_creates_venue_event_and_lineup(db_engine: AsyncEngine) -> None:
    """A first-seen event materializes venue, event, artists, and billing-ordered lineup."""
    discovered = make_discovered(artists=(("Headliner X", 0), ("Opener Y", 1)))
    result = await process_discovered(db_engine, discovered)

    assert result.is_new is True
    assert result.old_status is None
    assert len(result.artist_ids) == 2

    event = await _one(
        db_engine,
        "SELECT title, status::text AS status, source, external_id, venue_id"
        " FROM events WHERE id = :id",
        id=result.event_id,
    )
    assert event.title == "Test Show"
    assert event.status == "on_sale"
    assert event.source == "ticketmaster"
    assert event.venue_id == result.venue_id

    venue = await _one(
        db_engine,
        "SELECT name, source_ids ->> 'ticketmaster' AS tm_id FROM venues WHERE id = :id",
        id=result.venue_id,
    )
    assert venue.name == "Test Hall"
    assert venue.tm_id == "v-0001"

    lineup = await _one(
        db_engine,
        "SELECT array_agg(a.name ORDER BY ea.billing) AS names FROM event_artists ea"
        " JOIN artists a ON a.id = ea.artist_id WHERE ea.event_id = :id",
        id=result.event_id,
    )
    assert lineup.names == ["Headliner X", "Opener Y"]
    genres = await _scalar(db_engine, "SELECT genres FROM artists WHERE name = :n", n="Headliner X")
    assert genres == ["indie rock"]


async def test_processing_twice_is_idempotent(db_engine: AsyncEngine) -> None:
    """The same message consumed twice resolves to the same rows without duplicates."""
    discovered = make_discovered()
    first = await process_discovered(db_engine, discovered)
    second = await process_discovered(db_engine, discovered)

    assert second.event_id == first.event_id
    assert second.is_new is False
    assert second.old_status is None
    assert await _scalar(db_engine, "SELECT count(*) FROM events") == 1
    assert await _scalar(db_engine, "SELECT count(*) FROM venues WHERE name = 'Test Hall'") == 1
    assert await _scalar(db_engine, "SELECT count(*) FROM artists WHERE name = 'Test Artist'") == 1


async def test_status_change_is_detected_and_applied(db_engine: AsyncEngine) -> None:
    """A real status transition updates the row and surfaces old_status."""
    await process_discovered(db_engine, make_discovered(status="on_sale"))
    result = await process_discovered(db_engine, make_discovered(status="cancelled"))

    assert result.old_status == "on_sale"
    status = await _scalar(
        db_engine, "SELECT status::text FROM events WHERE id = :id", id=result.event_id
    )
    assert status == "cancelled"


async def test_offsale_transition_is_not_flagged(db_engine: AsyncEngine) -> None:
    """on_sale -> announced (the offsale mapping) is applied silently, not flagged."""
    await process_discovered(db_engine, make_discovered(status="on_sale"))
    result = await process_discovered(db_engine, make_discovered(status="announced"))

    assert result.old_status is None
    status = await _scalar(
        db_engine, "SELECT status::text FROM events WHERE id = :id", id=result.event_id
    )
    assert status == "announced"


async def test_venue_merges_onto_seeded_venue_by_name_and_city(db_engine: AsyncEngine) -> None:
    """A discovered venue matching a seeded venue's name+city reuses it and attaches the id."""
    discovered = make_discovered(venue_name="Newport Music Hall", venue_source_id="v-newport")
    result = await process_discovered(db_engine, discovered)

    venue = await _one(
        db_engine,
        "SELECT id, source_ids ->> 'ticketmaster' AS tm_id FROM venues"
        " WHERE name = 'Newport Music Hall'",
    )
    assert result.venue_id == venue.id
    assert venue.tm_id == "v-newport"
    assert (
        await _scalar(db_engine, "SELECT count(*) FROM venues WHERE name = 'Newport Music Hall'")
        == 1
    )


async def test_artist_reuse_preserves_seeded_embedding(db_engine: AsyncEngine) -> None:
    """A lineup naming a seeded artist reuses that row, keeping its embedding."""
    result = await process_discovered(db_engine, make_discovered(artists=(("Phoebe Bridgers", 0),)))
    artist = await _one(
        db_engine,
        "SELECT id, embedding IS NOT NULL AS has_embedding FROM artists"
        " WHERE name = 'Phoebe Bridgers'",
    )
    assert result.artist_ids == [artist.id]
    assert artist.has_embedding is True


async def test_lineup_prune_removes_dropped_artists(db_engine: AsyncEngine) -> None:
    """When a later message drops an artist from the lineup, its link is pruned."""
    await process_discovered(
        db_engine, make_discovered(artists=(("Headliner X", 0), ("Opener Y", 1)))
    )
    result = await process_discovered(db_engine, make_discovered(artists=(("Headliner X", 0),)))
    count = await _scalar(
        db_engine, "SELECT count(*) FROM event_artists WHERE event_id = :id", id=result.event_id
    )
    assert count == 1


async def test_cross_source_duplicate_merges_into_existing_event(db_engine: AsyncEngine) -> None:
    """A fuzzy-matching event from another source resolves to the existing row."""
    original = await process_discovered(
        db_engine,
        make_discovered(title="Turnstile: Never Enough Tour", artists=(("Turnstile", 0),)),
    )
    duplicate = await process_discovered(
        db_engine,
        make_discovered(
            source="songkick",
            external_id="sk-777",
            title="Turnstile - Never Enough Tour",
            starts_at=STARTS_AT + timedelta(minutes=5),
            venue_source_id="sk-venue-1",
            artists=(("Turnstile", 0), ("Speed", 1)),
        ),
    )

    assert duplicate.merged_cross_source is True
    assert duplicate.event_id == original.event_id
    assert await _scalar(db_engine, "SELECT count(*) FROM events") == 1
    # The second source's extra opener is linked, and nothing was pruned.
    count = await _scalar(
        db_engine,
        "SELECT count(*) FROM event_artists WHERE event_id = :id",
        id=original.event_id,
    )
    assert count == 2
