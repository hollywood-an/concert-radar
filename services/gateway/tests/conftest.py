"""Shared fixtures: a migrated + seeded Postgres testcontainer and an ASGI test client."""

import asyncio
import os
import time
import uuid
from collections.abc import AsyncIterator, Iterator, Sequence
from datetime import datetime
from pathlib import Path

import asyncpg
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession
from testcontainers.postgres import PostgresContainer

REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_VENUE_NAMES = [
    "Newport Music Hall",
    "Ace of Cups",
    "The Basement",
    "KEMBA Live!",
    "Nationwide Arena",
]


async def _connect_with_retry(dsn: str) -> asyncpg.Connection:
    """Connect to Postgres, retrying while the container finishes its first-boot init."""
    deadline = time.monotonic() + 90
    while True:
        try:
            return await asyncpg.connect(dsn)
        except (OSError, asyncpg.PostgresError):
            if time.monotonic() > deadline:
                raise
            await asyncio.sleep(1)


async def _prepare_database(dsn: str) -> None:
    """Apply every migration and seed file in filename order."""
    conn = await _connect_with_retry(dsn)
    try:
        for sql_file in sorted((REPO_ROOT / "db" / "migrations").glob("*.sql")):
            await conn.execute(sql_file.read_text())
        for sql_file in sorted((REPO_ROOT / "db" / "seeds").glob("*.sql")):
            await conn.execute(sql_file.read_text())
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Start the project Postgres image, migrate + seed it, and export DATABASE_URL."""
    container = PostgresContainer(
        image="concert-radar-postgres:latest",
        username="cr",
        password="cr_dev",
        dbname="concertradar",
        driver=None,
    )
    with container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(5432)
        asyncio.run(_prepare_database(f"postgresql://cr:cr_dev@{host}:{port}/concertradar"))
        url = f"postgresql+asyncpg://cr:cr_dev@{host}:{port}/concertradar"
        os.environ["DATABASE_URL"] = url
        yield url


@pytest.fixture(scope="session")
def app(database_url: str) -> FastAPI:
    """Import the FastAPI app after DATABASE_URL points at the test container."""
    from src.config import get_settings
    from src.deps import get_engine, get_sessionmaker

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    from src.main import app as application

    return application


@pytest.fixture(scope="session", autouse=True)
async def _dispose_engine(app: FastAPI) -> AsyncIterator[None]:
    """Dispose the app's engine when the test session ends."""
    yield
    from src.deps import get_engine

    await get_engine().dispose()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """HTTP client bound directly to the ASGI app."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.fixture
async def db(app: FastAPI) -> AsyncIterator[AsyncSession]:
    """Direct database session for test setup and assertions."""
    from src.deps import get_sessionmaker

    async with get_sessionmaker()() as session:
        yield session


@pytest.fixture(autouse=True)
async def _clean_tables(app: FastAPI) -> AsyncIterator[None]:
    """Reset mutable tables after each test, keeping the seeded artists and venues."""
    yield
    from src.deps import get_sessionmaker

    async with get_sessionmaker()() as session:
        await session.execute(
            text("TRUNCATE users, events, event_artists, follows, alerts_sent CASCADE")
        )
        await session.execute(
            text("DELETE FROM venues WHERE name NOT IN :names").bindparams(
                bindparam("names", expanding=True)
            ),
            {"names": SEED_VENUE_NAMES},
        )
        await session.commit()


async def auth_headers(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    """Log in via /auth/dev and return Authorization headers for that user."""
    response = await client.post("/auth/dev", json={"email": email})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


async def create_venue(session: AsyncSession, *, name: str, lon: float, lat: float) -> uuid.UUID:
    """Insert a venue at the given coordinates and return its id."""
    venue_id = (
        await session.execute(
            text(
                """
                INSERT INTO venues (name, location, city, state)
                VALUES (:name, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                        :city, :state)
                RETURNING id
                """
            ),
            {"name": name, "lon": lon, "lat": lat, "city": "Testville", "state": "XX"},
        )
    ).scalar_one()
    await session.commit()
    return uuid.UUID(str(venue_id))


async def create_event(
    session: AsyncSession,
    *,
    starts_at: datetime,
    status: str = "announced",
    venue_name: str = "Newport Music Hall",
    lineup: Sequence[tuple[str, int]] = (("The National", 0),),
    title: str = "Test Show",
) -> uuid.UUID:
    """Insert an event with the given lineup (artist name, billing) and return its id."""
    venue_id = (
        await session.execute(
            text("SELECT id FROM venues WHERE name = :name"), {"name": venue_name}
        )
    ).scalar_one()
    event_id = (
        await session.execute(
            text(
                """
                INSERT INTO events (venue_id, title, starts_at, status, source, external_id,
                                    price_min_cents, price_max_cents, source_url, image_url)
                VALUES (:venue_id, :title, :starts_at, CAST(:status AS event_status), 'test',
                        :external_id, 2500, 4500, 'https://tickets.example/e',
                        'https://img.example/e.jpg')
                RETURNING id
                """
            ),
            {
                "venue_id": venue_id,
                "title": title,
                "starts_at": starts_at,
                "status": status,
                "external_id": uuid.uuid4().hex,
            },
        )
    ).scalar_one()
    for artist_name, billing in lineup:
        artist_id = (
            await session.execute(
                text("SELECT id FROM artists WHERE name = :name"), {"name": artist_name}
            )
        ).scalar_one()
        await session.execute(
            text(
                "INSERT INTO event_artists (event_id, artist_id, billing)"
                " VALUES (:event_id, :artist_id, :billing)"
            ),
            {"event_id": event_id, "artist_id": artist_id, "billing": billing},
        )
    await session.commit()
    return uuid.UUID(str(event_id))
