"""gRPC client for the recommender service, behind GET /discover."""

from datetime import UTC
from functools import lru_cache
from typing import TYPE_CHECKING
from uuid import UUID

import grpc
import structlog

from src.config import get_settings
from src.gen.recommender.v1 import recommender_pb2, recommender_pb2_grpc
from src.schemas import DiscoverItem

if TYPE_CHECKING:
    from src.gen.recommender.v1.recommender_pb2_grpc import RecommenderServiceAsyncStub

logger = structlog.get_logger()


class RecommenderUnavailable(Exception):
    """The recommender failed, was unreachable, or missed the deadline."""


class RecommenderClient:
    """GetRecommendations with a per-call deadline."""

    def __init__(self, target: str, timeout_s: float) -> None:
        self._target = target
        self._timeout_s = timeout_s
        self._channel: grpc.aio.Channel | None = None
        self._stub: RecommenderServiceAsyncStub | None = None

    def _get_stub(self) -> "RecommenderServiceAsyncStub":
        # A grpc.aio channel binds to the event loop it was created on, so it is opened on
        # the first call, inside the server's loop, rather than at import.
        if self._stub is None:
            self._channel = grpc.aio.insecure_channel(self._target)
            self._stub = recommender_pb2_grpc.RecommenderServiceStub(self._channel)
        return self._stub

    async def aclose(self) -> None:
        """Close the channel if one was opened."""
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
            self._stub = None

    async def recommendations(self, user_id: UUID, limit: int) -> list[DiscoverItem]:
        """Return the user's discovery shows, or raise RecommenderUnavailable."""
        request = recommender_pb2.GetRecommendationsRequest(user_id=str(user_id), limit=limit)
        try:
            response = await self._get_stub().GetRecommendations(request, timeout=self._timeout_s)
        except grpc.aio.AioRpcError as exc:
            logger.warning("recommender call failed", code=exc.code().name)
            raise RecommenderUnavailable(exc.code().name) from exc
        return [_to_item(r) for r in response.recommendations]


def _to_item(message: recommender_pb2.Recommendation) -> DiscoverItem:
    return DiscoverItem(
        event_id=UUID(message.event_id),
        title=message.title if message.HasField("title") else None,
        starts_at=message.starts_at.ToDatetime(tzinfo=UTC),
        venue_name=message.venue_name,
        venue_city=message.venue_city if message.HasField("venue_city") else None,
        distance_m=message.distance_m,
        image_url=message.image_url if message.HasField("image_url") else None,
        artist_id=UUID(message.artist_id),
        artist_name=message.artist_name,
        artist_image_url=message.artist_image_url if message.HasField("artist_image_url") else None,
        genre=message.genre,
        similarity=message.similarity,
    )


@lru_cache
def get_recommender() -> RecommenderClient:
    """Return the process-wide recommender client built from settings."""
    settings = get_settings()
    return RecommenderClient(settings.recommender_target, settings.recommender_timeout_s)
