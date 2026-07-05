"""Shared fixtures: migrated+seeded Postgres, a Redpanda broker, and row factories."""

import asyncio
from collections.abc import AsyncIterator, Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.kafka import RedpandaContainer
from testcontainers.postgres import PostgresContainer

from src.schemas import EnrichedEvent

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


async def create_user(
    engine: AsyncEngine,
    email: str,
    *,
    lon: float = -82.9988,
    lat: float = 39.9612,
    follows: Sequence[str] = (),
) -> UUID:
    """Insert a user homed at the given point; following artists sets a taste embedding."""
    async with engine.begin() as conn:
        user_id = (
            await conn.execute(
                text(
                    "INSERT INTO users (email, home_location) VALUES"
                    " (:email, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography)"
                    " RETURNING id"
                ),
                {"email": email, "lon": lon, "lat": lat},
            )
        ).scalar_one()
        for artist_name in follows:
            await conn.execute(
                text(
                    "INSERT INTO follows (user_id, artist_id)"
                    " SELECT :user_id, id FROM artists WHERE name = :name"
                ),
                {"user_id": user_id, "name": artist_name},
            )
        if follows:
            await conn.execute(
                text("SELECT update_user_taste_embedding(:user_id)"), {"user_id": user_id}
            )
    return UUID(str(user_id))


async def create_event(
    engine: AsyncEngine,
    *,
    artist_name: str = "Phoebe Bridgers",
    venue_name: str = "Newport Music Hall",
    starts_at: datetime = STARTS_AT,
    status: str = "on_sale",
    external_id: str = "match-0001",
) -> tuple[UUID, UUID, UUID]:
    """Insert an event at a seeded venue; return (event_id, venue_id, artist_id)."""
    async with engine.begin() as conn:
        venue_id = (
            await conn.execute(
                text("SELECT id FROM venues WHERE name = :name"), {"name": venue_name}
            )
        ).scalar_one()
        artist_id = (
            await conn.execute(
                text("SELECT id FROM artists WHERE name = :name"), {"name": artist_name}
            )
        ).scalar_one()
        event_id = (
            await conn.execute(
                text(
                    "INSERT INTO events (venue_id, title, starts_at, status, source, external_id)"
                    " VALUES (:venue_id, :title, :starts_at, cast(:status AS event_status),"
                    " 'ticketmaster', :external_id) RETURNING id"
                ),
                {
                    "venue_id": venue_id,
                    "title": f"{artist_name} Live",
                    "starts_at": starts_at,
                    "status": status,
                    "external_id": external_id,
                },
            )
        ).scalar_one()
        await conn.execute(
            text(
                "INSERT INTO event_artists (event_id, artist_id, billing)"
                " VALUES (:event_id, :artist_id, 0)"
            ),
            {"event_id": event_id, "artist_id": artist_id},
        )
    return UUID(str(event_id)), UUID(str(venue_id)), UUID(str(artist_id))


def make_enriched(event_id: UUID, venue_id: UUID, artist_ids: Sequence[UUID]) -> EnrichedEvent:
    """Build the events.enriched payload the enricher would publish for this event."""
    return EnrichedEvent(
        event_id=event_id,
        venue_id=venue_id,
        artist_ids=list(artist_ids),
        enriched_artist_ids=list(artist_ids),
        title="Enriched Show",
        starts_at=STARTS_AT,
        status="on_sale",
    )
