"""Shared fixtures: migrated+seeded Postgres, a Redpanda broker, and a message factory."""

import asyncio
from collections.abc import AsyncIterator, Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.kafka import RedpandaContainer
from testcontainers.postgres import PostgresContainer

from src.schemas import DiscoveredArtist, DiscoveredEvent, DiscoveredVenue

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


def make_discovered(
    *,
    source: str = "ticketmaster",
    external_id: str = "tm-0001",
    title: str = "Test Show",
    status: str = "on_sale",
    starts_at: datetime = STARTS_AT,
    venue_name: str = "Test Hall",
    venue_source_id: str = "v-0001",
    city: str | None = "Columbus",
    artists: Sequence[tuple[str, int]] = (("Test Artist", 0),),
    genres: Sequence[str] = ("indie rock",),
) -> DiscoveredEvent:
    """Build an events.discovered payload with sensible Columbus defaults."""
    return DiscoveredEvent(
        source=source,
        external_id=external_id,
        title=title,
        source_url=f"https://tickets.example/{external_id}",
        starts_at=starts_at,
        price_min_cents=2500,
        price_max_cents=4500,
        currency="USD",
        image_url=f"https://img.example/{external_id}.jpg",
        status=status,
        venue=DiscoveredVenue(
            tm_id=venue_source_id,
            name=venue_name,
            city=city,
            state="OH",
            country="US",
            address={"line1": "1 Test St"},
            longitude=-83.0007,
            latitude=39.9612,
        ),
        artists=[
            DiscoveredArtist(name=name, tm_id=f"a-{i}", genres=list(genres), billing=billing)
            for i, (name, billing) in enumerate(artists)
        ],
    )


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
        await conn.execute(text("TRUNCATE event_artists, alerts_sent, events"))
        await conn.execute(
            text("DELETE FROM artists WHERE NOT (name = ANY(:names))"),
            {"names": list(SEED_ARTIST_NAMES)},
        )
        await conn.execute(
            text("DELETE FROM venues WHERE NOT (name = ANY(:names))"),
            {"names": list(SEED_VENUE_NAMES)},
        )
        await conn.execute(text("UPDATE venues SET source_ids = '{}'::jsonb"))
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
