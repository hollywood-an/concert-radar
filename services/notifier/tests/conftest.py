"""Shared fixtures: migrated+seeded Postgres, a Redpanda broker, and row factories."""

import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, time
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

from src.schemas import MatchProposed

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
    alert_email: bool = True,
    quiet_hours_start: time | None = None,
    quiet_hours_end: time | None = None,
) -> UUID:
    """Insert a user with the given alert preferences and return its id."""
    async with engine.begin() as conn:
        user_id = (
            await conn.execute(
                text(
                    "INSERT INTO users (email, alert_email, quiet_hours_start, quiet_hours_end)"
                    " VALUES (:email, :alert_email, :start, :end) RETURNING id"
                ),
                {
                    "email": email,
                    "alert_email": alert_email,
                    "start": quiet_hours_start,
                    "end": quiet_hours_end,
                },
            )
        ).scalar_one()
    return UUID(str(user_id))


async def create_event(engine: AsyncEngine, *, external_id: str = "notify-0001") -> UUID:
    """Insert a Phoebe Bridgers event at a seeded venue and return its id."""
    async with engine.begin() as conn:
        event_id = (
            await conn.execute(
                text(
                    "INSERT INTO events (venue_id, title, starts_at, status, source, external_id)"
                    " SELECT v.id, 'Phoebe Bridgers Live', :starts_at, 'on_sale',"
                    " 'ticketmaster', :external_id"
                    " FROM venues v WHERE v.name = 'Newport Music Hall' RETURNING id"
                ),
                {"starts_at": STARTS_AT, "external_id": external_id},
            )
        ).scalar_one()
        await conn.execute(
            text(
                "INSERT INTO event_artists (event_id, artist_id, billing)"
                " SELECT :event_id, id, 0 FROM artists WHERE name = 'Phoebe Bridgers'"
            ),
            {"event_id": event_id},
        )
    return UUID(str(event_id))


def make_match(user_id: UUID, event_id: UUID, score: float = 0.72) -> MatchProposed:
    """Build the matches.proposed payload the matcher would publish."""
    return MatchProposed(user_id=user_id, event_id=event_id, score=score)
