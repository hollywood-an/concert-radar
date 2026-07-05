"""OpenTelemetry tracing and structlog configuration shared by every entrypoint."""

import os

import structlog
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from structlog.typing import EventDict, Processor, WrappedLogger


def _trace_context_injector(service_name: str) -> Processor:
    """Build a structlog processor that stamps trace_id, span_id, service_name on every line."""

    def inject(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
        """Copy the active OTel span context into the log event dict."""
        context = trace.get_current_span().get_span_context()
        event_dict["trace_id"] = format(context.trace_id, "032x")
        event_dict["span_id"] = format(context.span_id, "016x")
        event_dict["service_name"] = service_name
        return event_dict

    return inject


def setup_telemetry(service_name: str) -> TracerProvider:
    """Configure OTLP gRPC tracing and structlog; return the provider for flushing at exit."""
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            _trace_context_injector(service_name),
            structlog.processors.JSONRenderer(),
        ],
    )
    return provider
