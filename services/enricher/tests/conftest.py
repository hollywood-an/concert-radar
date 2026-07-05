"""Shared fixtures: migrated+seeded Postgres, MusicBrainz mock transport, row factories."""

import asyncio
import json
from collections.abc import AsyncIterator, Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg
import httpx
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.kafka import RedpandaContainer
from testcontainers.postgres import PostgresContainer

from src.schemas import DedupedEvent

REPO_ROOT = Path(__file__).resolve().parents[3]

SEED_ARTIST_NAMES = (
    "The National",
    "Phoebe Bridgers",
    "Turnstile",
    "Japanese Breakfast",
    "Khruangbin",
    "Sylvan Esso",
    "Jason Isbell",
    "Denzel Curry",
    "Caroline Polachek",
    "Mannequin Pussy",
)

SEED_VENUE_NAMES = (
    "Newport Music Hall",
    "Ace of Cups",
    "The Basement",
    "KEMBA Live!",
    "Nationwide Arena",
)

STARTS_AT = datetime(2026, 11, 20, 1, 0, tzinfo=UTC)


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Start Postgres in a container, apply all migrations and seeds, and yield the async URL."""
    with PostgresContainer(
        "concert-radar-postgres:latest",
        username="cr",
        password="cr_dev",
        dbname="concertradar",
        driver="asyncpg",
    ) as container:
        url = container.get_connection_url()
        sql_files = [
            *sorted((REPO_ROOT / "db" / "migrations").glob("*.sql")),
            REPO_ROOT / "db" / "seeds" / "genres.sql",
            REPO_ROOT / "db" / "seeds" / "sample_venues.sql",
        ]
        asyncio.run(_apply_sql_files(url, sql_files))
        yield url


async def _apply_sql_files(url: str, paths: list[Path]) -> None:
    """Execute each SQL file in order over one asyncpg connection."""
    conn = await asyncpg.connect(url.replace("postgresql+asyncpg", "postgresql"))
    try:
        for path in paths:
            await conn.execute(path.read_text())
    finally:
        await conn.close()


@pytest.fixture
async def db_engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    """Yield an engine over a database reset to its freshly seeded state."""
    engine = create_async_engine(database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE event_artists, follows, alerts_sent, users, events"))
        await conn.execute(
            text("DELETE FROM artists WHERE NOT (name = ANY(:names))"),
            {"names": list(SEED_ARTIST_NAMES)},
        )
        await conn.execute(
            text("DELETE FROM venues WHERE NOT (name = ANY(:names))"),
            {"names": list(SEED_VENUE_NAMES)},
        )
        await conn.execute(text("UPDATE artists SET mbid = NULL, spotify_id = NULL"))
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
def kafka_bootstrap() -> Iterator[str]:
    """Start Redpanda in a container and yield its bootstrap server address."""
    with RedpandaContainer("docker.redpanda.com/redpandadata/redpanda:v24.1.1") as container:
        yield container.get_bootstrap_server()


@pytest.fixture(scope="session", autouse=True)
def _tracer_provider() -> None:
    """Install a real tracer provider so spans carry valid, injectable contexts."""
    trace.set_tracer_provider(TracerProvider())


def mb_artist_json(
    mbid: str,
    name: str,
    score: int = 100,
    tags: Sequence[tuple[str, int]] = (("indie rock", 5), ("shoegaze", 2)),
) -> dict[str, Any]:
    """Build a MusicBrainz artist search response with one result."""
    return {
        "artists": [
            {
                "id": mbid,
                "name": name,
                "score": score,
                "tags": [{"name": tag, "count": count} for tag, count in tags],
            }
        ]
    }


def mb_transport(
    responses: dict[str, dict[str, Any]], calls: list[str] | None = None
) -> httpx.MockTransport:
    """Serve canned MusicBrainz search responses keyed by the queried artist name."""

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["query"]
        assert query.startswith('artist:"') and query.endswith('"')
        name = query[len('artist:"') : -1]
        if calls is not None:
            calls.append(name)
        return httpx.Response(
            200,
            json=responses.get(name, {"artists": []}),
            headers={"Content-Type": "application/json"},
        )

    return httpx.MockTransport(handler)


async def create_artist(engine: AsyncEngine, name: str, genres: Sequence[str] = ()) -> UUID:
    """Insert a stub artist the way the deduper does and return its id."""
    async with engine.begin() as conn:
        row = (
            await conn.execute(
                text("INSERT INTO artists (name, genres) VALUES (:name, :genres) RETURNING id"),
                {"name": name, "genres": list(genres)},
            )
        ).one()
    return UUID(str(row[0]))


async def create_event(engine: AsyncEngine, artist_ids: Sequence[UUID]) -> tuple[UUID, UUID]:
    """Insert an event at a seeded venue with the given lineup; return (event_id, venue_id)."""
    async with engine.begin() as conn:
        venue_id = (
            await conn.execute(text("SELECT id FROM venues WHERE name = 'Newport Music Hall'"))
        ).scalar_one()
        event_id = (
            await conn.execute(
                text(
                    "INSERT INTO events (venue_id, title, starts_at, status, source, external_id)"
                    " VALUES (:venue_id, 'Enrich Test Show', :starts_at,"
                    " 'on_sale', 'ticketmaster', :external_id) RETURNING id"
                ),
                {
                    "venue_id": venue_id,
                    "starts_at": STARTS_AT,
                    "external_id": f"enrich-{artist_ids[0]}",
                },
            )
        ).scalar_one()
        for billing, artist_id in enumerate(artist_ids):
            await conn.execute(
                text(
                    "INSERT INTO event_artists (event_id, artist_id, billing)"
                    " VALUES (:event_id, :artist_id, :billing)"
                ),
                {"event_id": event_id, "artist_id": artist_id, "billing": billing},
            )
    return UUID(str(event_id)), UUID(str(venue_id))


def make_deduped(event_id: UUID, venue_id: UUID, artist_ids: Sequence[UUID]) -> DedupedEvent:
    """Build the events.deduped payload the deduper would publish for this event."""
    return DedupedEvent(
        event_id=event_id,
        venue_id=venue_id,
        artist_ids=list(artist_ids),
        source="ticketmaster",
        external_id=f"enrich-{artist_ids[0] if artist_ids else 'none'}",
        title="Enrich Test Show",
        starts_at=STARTS_AT,
        status="on_sale",
        is_new=True,
    )


def parse_vector(literal: str) -> list[float]:
    """Parse a pgvector text literal into floats."""
    values: list[float] = json.loads(literal)
    return values
