"""Tests for POST /events/:id/dismiss and its effect on the feed."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_headers, create_event

FUTURE = datetime.now(UTC) + timedelta(days=30)


async def test_dismiss_requires_auth(client: httpx.AsyncClient) -> None:
    """Dismissing without a Bearer token is rejected with 401."""
    response = await client.post(f"/events/{uuid.uuid4()}/dismiss")
    assert response.status_code == 401


async def test_dismiss_unknown_event_returns_404(client: httpx.AsyncClient) -> None:
    """Dismissing a nonexistent event fails with 404."""
    headers = await auth_headers(client, "dismiss404@example.com")
    response = await client.post(f"/events/{uuid.uuid4()}/dismiss", headers=headers)
    assert response.status_code == 404


async def test_dismissed_event_leaves_the_feed(client: httpx.AsyncClient, db: AsyncSession) -> None:
    """A dismissed event disappears from the dismissing user's feed only."""
    event_id = await create_event(db, starts_at=FUTURE)
    dismisser = await auth_headers(client, "dismisser@example.com")
    bystander = await auth_headers(client, "bystander@example.com")

    assert len((await client.get("/feed", headers=dismisser)).json()["items"]) == 1
    response = await client.post(f"/events/{event_id}/dismiss", headers=dismisser)
    assert response.status_code == 204

    assert (await client.get("/feed", headers=dismisser)).json()["items"] == []
    assert len((await client.get("/feed", headers=bystander)).json()["items"]) == 1


async def test_dismiss_is_idempotent(client: httpx.AsyncClient, db: AsyncSession) -> None:
    """Dismissing the same event twice succeeds."""
    event_id = await create_event(db, starts_at=FUTURE)
    headers = await auth_headers(client, "twice-dismiss@example.com")
    first = await client.post(f"/events/{event_id}/dismiss", headers=headers)
    second = await client.post(f"/events/{event_id}/dismiss", headers=headers)
    assert first.status_code == second.status_code == 204
