"""GET /discover against an in-process recommender served over a real gRPC channel."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import grpc
import httpx
import pytest
from google.protobuf.timestamp_pb2 import Timestamp

from src.gen.recommender.v1 import recommender_pb2, recommender_pb2_grpc
from src.recommender import RecommenderClient
from tests.conftest import auth_headers

STARTS_AT = datetime(2026, 12, 4, 1, 0, tzinfo=UTC)


def _recommendations() -> list[recommender_pb2.Recommendation]:
    starts_at = Timestamp()
    starts_at.FromDatetime(STARTS_AT)
    return [
        recommender_pb2.Recommendation(
            event_id="11111111-1111-1111-1111-111111111111",
            title="Fall Tour",
            starts_at=starts_at,
            venue_name="Newport Music Hall",
            venue_city="Columbus",
            distance_m=3200.5,
            image_url="https://img.example/e.jpg",
            artist_id="22222222-2222-2222-2222-222222222222",
            artist_name="Wet Leg",
            artist_image_url="https://img.example/a.jpg",
            genre="indie rock",
            similarity=0.91,
        ),
        recommender_pb2.Recommendation(
            event_id="33333333-3333-3333-3333-333333333333",
            starts_at=starts_at,
            venue_name="The Basement",
            distance_m=1200.0,
            artist_id="44444444-4444-4444-4444-444444444444",
            artist_name="No Extras",
            similarity=0.42,
        ),
    ]


class FakeRecommender(recommender_pb2_grpc.RecommenderServiceServicer):
    """Answers with fixed recommendations, optionally after a delay; records each request."""

    def __init__(self, delay_s: float = 0) -> None:
        self.requests: list[recommender_pb2.GetRecommendationsRequest] = []
        self.delay_s = delay_s

    async def GetRecommendations(
        self,
        request: recommender_pb2.GetRecommendationsRequest,
        context: grpc.aio.ServicerContext[
            recommender_pb2.GetRecommendationsRequest,
            recommender_pb2.GetRecommendationsResponse,
        ],
    ) -> recommender_pb2.GetRecommendationsResponse:
        self.requests.append(request)
        await asyncio.sleep(self.delay_s)
        return recommender_pb2.GetRecommendationsResponse(recommendations=_recommendations())


@asynccontextmanager
async def serving(
    monkeypatch: pytest.MonkeyPatch, servicer: FakeRecommender, timeout_s: float = 2.0
) -> AsyncIterator[FakeRecommender]:
    """Serve the fake on a free port and point GET /discover at it for the block."""
    from src.routes import discover as discover_routes

    server = grpc.aio.server()
    recommender_pb2_grpc.add_RecommenderServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    client = RecommenderClient(f"127.0.0.1:{port}", timeout_s)
    monkeypatch.setattr(discover_routes, "get_recommender", lambda: client)
    try:
        yield servicer
    finally:
        await client.aclose()
        await server.stop(None)


@pytest.fixture
async def recommender(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FakeRecommender]:
    """A fake recommender that answers immediately."""
    async with serving(monkeypatch, FakeRecommender()) as servicer:
        yield servicer


@pytest.fixture
async def slow_recommender(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[FakeRecommender]:
    """A fake recommender slower than the client's 0.2 s deadline."""
    async with serving(monkeypatch, FakeRecommender(delay_s=1.0), timeout_s=0.2) as servicer:
        yield servicer


async def test_discover_returns_the_recommenders_shows(
    client: httpx.AsyncClient, recommender: FakeRecommender
) -> None:
    headers = await auth_headers(client, "discover@example.com")
    me = (await client.get("/me", headers=headers)).json()

    response = await client.get("/discover", params={"limit": 5}, headers=headers)

    assert response.status_code == 200
    assert response.json() == [
        {
            "event_id": "11111111-1111-1111-1111-111111111111",
            "title": "Fall Tour",
            "starts_at": "2026-12-04T01:00:00Z",
            "venue_name": "Newport Music Hall",
            "venue_city": "Columbus",
            "distance_m": 3200.5,
            "image_url": "https://img.example/e.jpg",
            "artist_id": "22222222-2222-2222-2222-222222222222",
            "artist_name": "Wet Leg",
            "artist_image_url": "https://img.example/a.jpg",
            "genre": "indie rock",
            "similarity": 0.91,
        },
        {
            "event_id": "33333333-3333-3333-3333-333333333333",
            "title": None,
            "starts_at": "2026-12-04T01:00:00Z",
            "venue_name": "The Basement",
            "venue_city": None,
            "distance_m": 1200.0,
            "image_url": None,
            "artist_id": "44444444-4444-4444-4444-444444444444",
            "artist_name": "No Extras",
            "artist_image_url": None,
            "genre": "",
            "similarity": 0.42,
        },
    ]
    assert [(r.user_id, r.limit) for r in recommender.requests] == [(me["id"], 5)]


async def test_discover_requires_sign_in(
    client: httpx.AsyncClient, recommender: FakeRecommender
) -> None:
    response = await client.get("/discover")

    assert response.status_code == 401
    assert recommender.requests == []


@pytest.mark.parametrize("limit", [0, 51])
async def test_discover_rejects_out_of_range_limits(
    client: httpx.AsyncClient, recommender: FakeRecommender, limit: int
) -> None:
    headers = await auth_headers(client, "discover@example.com")

    response = await client.get("/discover", params={"limit": limit}, headers=headers)

    assert response.status_code == 422
    assert recommender.requests == []


async def test_discover_answers_503_past_the_deadline(
    client: httpx.AsyncClient, slow_recommender: FakeRecommender
) -> None:
    headers = await auth_headers(client, "discover@example.com")

    response = await client.get("/discover", headers=headers)

    assert response.status_code == 503
    assert len(slow_recommender.requests) == 1


async def test_discover_answers_503_when_the_recommender_is_down(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.routes import discover as discover_routes

    # Nothing listens on port 1.
    down = RecommenderClient("127.0.0.1:1", timeout_s=2.0)
    monkeypatch.setattr(discover_routes, "get_recommender", lambda: down)
    headers = await auth_headers(client, "discover@example.com")

    response = await client.get("/discover", headers=headers)

    assert response.status_code == 503
    await down.aclose()
