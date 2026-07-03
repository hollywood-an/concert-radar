"""Shared fixtures: the saved API payload and a migrated, seeded Postgres container."""

import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import asyncpg
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ticketmaster_columbus.json"

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


@pytest.fixture
def payload() -> dict[str, Any]:
    """Load the saved Discovery API fixture page."""
    data: dict[str, Any] = json.loads(FIXTURE_PATH.read_text())
    return data


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
