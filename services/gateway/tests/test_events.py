"""Tests for GET /events/{id}."""

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import create_event


async def test_event_detail_returns_venue_and_billing_ordered_artists(
    client: httpx.AsyncClient, db: AsyncSession
) -> None:
    """The detail response embeds venue coordinates and lists artists ordered by billing."""
    event_id = await create_event(
        db,
        starts_at=datetime.now(UTC) + timedelta(days=14),
        lineup=(("Phoebe Bridgers", 1), ("The National", 0)),
        title="Double Bill",
    )
    response = await client.get(f"/events/{event_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(event_id)
    assert body["title"] == "Double Bill"
    assert body["status"] == "announced"
    assert body["venue"]["name"] == "Newport Music Hall"
    assert body["venue"]["city"] == "Columbus"
    assert body["venue"]["state"] == "OH"
    assert body["venue"]["location"]["lat"] == pytest.approx(39.9979)
    assert body["venue"]["location"]["lon"] == pytest.approx(-83.0083)
    assert [a["name"] for a in body["artists"]] == ["The National", "Phoebe Bridgers"]
    assert [a["billing"] for a in body["artists"]] == [0, 1]
    assert body["artists"][0]["genres"] == ["indie rock", "chamber pop", "post-punk revival"]


async def test_event_detail_unknown_uuid_returns_404(client: httpx.AsyncClient) -> None:
    """An unknown event id yields 404."""
    response = await client.get(f"/events/{uuid.uuid4()}")
    assert response.status_code == 404
