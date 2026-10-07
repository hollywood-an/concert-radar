"""Shared fixtures: a migrated Postgres, the gRPC server on a free port, and row factories."""

import asyncio
from collections.abc import AsyncIterator, Iterator, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

import asyncpg
import grpc
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer

from src.gen.recommender.v1 import recommender_pb2_grpc
from src.main import start_grpc_server

if TYPE_CHECKING:
    from src.gen.recommender.v1.recommender_pb2_grpc import RecommenderServiceAsyncStub

REPO_ROOT = Path(__file__).resolve().parents[3]
EMBEDDING_DIMENSIONS = 384
# Seeded venues in Columbus, OH; the default user lives downtown.
NEAR_VENUE = "Newport Music Hall"
OTHER_NEAR_VENUE = "KEMBA Live!"
COLUMBUS = (-82.9988, 39.9612)


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Start Postgres in a container, apply all migrations and the venue seed, yield the URL."""
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
    """Yield an engine over a database with no users, artists, or events."""
    engine = create_async_engine(database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE users, artists, events CASCADE"))
    yield engine
    await engine.dispose()


@pytest.fixture
async def stub(db_engine: AsyncEngine) -> AsyncIterator["RecommenderServiceAsyncStub"]:
    """Serve the recommender on a free port and yield a client stub connected to it."""
    server, port = await start_grpc_server(db_engine, 0)
    channel = grpc.aio.insecure_channel(f"localhost:{port}")
    try:
        yield recommender_pb2_grpc.RecommenderServiceStub(channel)
    finally:
        await channel.close()
        await server.stop(None)


def embedding(**weights: float) -> str:
    """Build a pgvector literal with the given weights at named axes (x, y, z) and 0 elsewhere."""
    axes = {"x": 0, "y": 1, "z": 2}
    values = [0.0] * EMBEDDING_DIMENSIONS
    for axis, weight in weights.items():
        values[axes[axis]] = weight
    return "[" + ",".join(str(v) for v in values) + "]"


async def create_artist(
    engine: AsyncEngine, name: str, genres: Sequence[str], vector: str | None
) -> UUID:
    """Insert an artist with the given genres and embedding; return its id."""
    async with engine.begin() as conn:
        artist_id = (
            await conn.execute(
                text(
                    "INSERT INTO artists (name, genres, embedding)"
                    " VALUES (:name, :genres, CAST(:embedding AS vector)) RETURNING id"
                ),
                {"name": name, "genres": list(genres), "embedding": vector},
            )
        ).scalar_one()
    return UUID(str(artist_id))


async def create_user(
    engine: AsyncEngine,
    email: str,
    *,
    follows: Sequence[UUID] = (),
    home: tuple[float, float] | None = COLUMBUS,
    radius_m: int = 80_000,
) -> UUID:
    """Insert a user; following artists sets the taste embedding the way the gateway does."""
    async with engine.begin() as conn:
        user_id = (
            await conn.execute(
                text(
                    "INSERT INTO users (email, home_location, travel_radius_m) VALUES (:email,"
                    " CASE WHEN CAST(:lon AS float) IS NULL THEN NULL ELSE"
                    " ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography END, :radius)"
                    " RETURNING id"
                ),
                {
                    "email": email,
                    "lon": home[0] if home else None,
                    "lat": home[1] if home else None,
                    "radius": radius_m,
                },
            )
        ).scalar_one()
        for artist_id in follows:
            await conn.execute(
                text("INSERT INTO follows (user_id, artist_id) VALUES (:user_id, :artist_id)"),
                {"user_id": user_id, "artist_id": artist_id},
            )
        await conn.execute(
            text("SELECT update_user_taste_embedding(:user_id)"), {"user_id": user_id}
        )
    return UUID(str(user_id))


async def create_show(
    engine: AsyncEngine,
    headliner: UUID,
    *,
    venue_name: str = NEAR_VENUE,
    days_out: float = 30,
    status: str = "on_sale",
) -> UUID:
    """Insert a show headlined by the artist at a seeded venue; return the event id."""
    starts_at = datetime.now(UTC) + timedelta(days=days_out)
    async with engine.begin() as conn:
        event_id = (
            await conn.execute(
                text(
                    "INSERT INTO events (venue_id, title, starts_at, status, source, external_id)"
                    " SELECT id, 'Live', :starts_at, CAST(:status AS event_status), 'test',"
                    " gen_random_uuid()::text FROM venues WHERE name = :venue RETURNING id"
                ),
                {"starts_at": starts_at, "status": status, "venue": venue_name},
            )
        ).scalar_one()
        await conn.execute(
            text(
                "INSERT INTO event_artists (event_id, artist_id, billing)"
                " VALUES (:event_id, :artist_id, 0)"
            ),
            {"event_id": event_id, "artist_id": headliner},
        )
    return UUID(str(event_id))
