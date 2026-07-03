"""OpenTelemetry tracing and structlog configuration shared by all entrypoints."""

import logging
import os

import structlog
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from structlog.typing import EventDict, WrappedLogger

_service_name = "unknown"
_configured = False


def _inject_trace_context(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    """Add trace_id, span_id, and service_name from the active OTel span to every log line."""
    ctx = trace.get_current_span().get_span_context()
    event_dict["trace_id"] = format(ctx.trace_id, "032x") if ctx.is_valid else "0" * 32
    event_dict["span_id"] = format(ctx.span_id, "016x") if ctx.is_valid else "0" * 16
    event_dict["service_name"] = _service_name
    return event_dict


def configure_telemetry(service_name: str) -> None:
    """Configure the OTLP gRPC trace exporter and structlog with trace-context injection."""
    global _service_name, _configured
    _service_name = service_name
    if _configured:
        return
    _configured = True

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            _inject_trace_context,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )
