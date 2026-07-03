"""Tests for /healthz and /readyz."""

import httpx


async def test_healthz(client: httpx.AsyncClient) -> None:
    """/healthz reports liveness without touching the database."""
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_with_reachable_database(client: httpx.AsyncClient) -> None:
    """/readyz returns ok when the database answers SELECT 1."""
    response = await client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
