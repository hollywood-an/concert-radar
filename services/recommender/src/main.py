"""gRPC server for recommender.v1.RecommenderService, with HTTP health checks beside it."""

import asyncio
import signal
from uuid import UUID

import grpc
import structlog
from google.protobuf.timestamp_pb2 import Timestamp
from opentelemetry import trace
from opentelemetry.instrumentation.grpc import GrpcAioInstrumentorServer
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.config import Settings
from src.gen.recommender.v1 import recommender_pb2, recommender_pb2_grpc
from src.health import start_health_server
from src.recommend import Recommendation, recommend
from src.telemetry import setup_telemetry

SERVICE_NAME = "recommender"
DEFAULT_LIMIT = 10
MAX_LIMIT = 50
# Seconds in-flight calls get to finish after SIGTERM before the server cancels them.
_SHUTDOWN_GRACE_S = 5.0

logger = structlog.get_logger()
tracer = trace.get_tracer(SERVICE_NAME)


class RecommenderService(recommender_pb2_grpc.RecommenderServiceServicer):
    """Answers GetRecommendations from Postgres."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def GetRecommendations(
        self,
        request: recommender_pb2.GetRecommendationsRequest,
        context: grpc.aio.ServicerContext[
            recommender_pb2.GetRecommendationsRequest,
            recommender_pb2.GetRecommendationsResponse,
        ],
    ) -> recommender_pb2.GetRecommendationsResponse:
        """Rank discovery shows for one user."""
        try:
            user_id = UUID(request.user_id)
        except ValueError:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "user_id must be a UUID")
        if request.limit < 0:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "limit must not be negative")
        limit = min(request.limit or DEFAULT_LIMIT, MAX_LIMIT)
        with tracer.start_as_current_span("recommend", attributes={"limit": limit}):
            recommendations = await recommend(self._engine, user_id, limit)
        if recommendations is None:
            await context.abort(grpc.StatusCode.NOT_FOUND, "user not found")
        logger.info("recommended", user_id=str(user_id), count=len(recommendations))
        return recommender_pb2.GetRecommendationsResponse(
            recommendations=[_to_message(r) for r in recommendations]
        )


def _to_message(recommendation: Recommendation) -> recommender_pb2.Recommendation:
    starts_at = Timestamp()
    starts_at.FromDatetime(recommendation.starts_at)
    return recommender_pb2.Recommendation(
        event_id=str(recommendation.event_id),
        title=recommendation.title,
        starts_at=starts_at,
        venue_name=recommendation.venue_name,
        venue_city=recommendation.venue_city,
        distance_m=recommendation.distance_m,
        image_url=recommendation.image_url,
        artist_id=str(recommendation.artist_id),
        artist_name=recommendation.artist_name,
        artist_image_url=recommendation.artist_image_url,
        genre=recommendation.genre,
        similarity=recommendation.similarity,
    )


async def start_grpc_server(engine: AsyncEngine, port: int) -> tuple[grpc.aio.Server, int]:
    """Start serving on all interfaces; return the server and its port (0 picks a free one)."""
    server = grpc.aio.server()
    recommender_pb2_grpc.add_RecommenderServiceServicer_to_server(
        RecommenderService(engine), server
    )
    bound_port = server.add_insecure_port(f"[::]:{port}")
    await server.start()
    return server, bound_port


def main() -> None:
    """Configure telemetry and serve until SIGTERM or Ctrl-C."""
    provider = setup_telemetry(SERVICE_NAME)
    GrpcAioInstrumentorServer().instrument()  # type: ignore[no-untyped-call]
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("shutting down")
    finally:
        provider.shutdown()


async def run() -> None:
    """Serve gRPC and the health endpoints until SIGTERM."""
    settings = Settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    serving = asyncio.Event()
    health_server = await start_health_server(settings.health_port, engine, serving)
    server, port = await start_grpc_server(engine, settings.grpc_port)
    serving.set()
    stop = asyncio.Event()
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stop.set)
    logger.info("serving", port=port)
    try:
        await stop.wait()
    finally:
        serving.clear()
        await server.stop(_SHUTDOWN_GRACE_S)
        health_server.close()
        await health_server.wait_closed()
        await engine.dispose()


if __name__ == "__main__":
    main()
