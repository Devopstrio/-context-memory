"""OpenTelemetry tracing configuration for distributed tracing."""

import structlog
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import (
    DEPLOYMENT_ENVIRONMENT,
    SERVICE_NAME,
    SERVICE_VERSION,
    Resource,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

from context_memory.config.settings import get_settings

logger = structlog.get_logger(__name__)


def setup_tracing() -> TracerProvider | None:
    """Configure OpenTelemetry tracing with OTLP exporter."""
    settings = get_settings()
    if not settings.otlp_enabled:
        logger.info("OpenTelemetry tracing is disabled")
        return None

    try:
        resource = Resource.create(
            {
                SERVICE_NAME: settings.otlp_service_name,
                SERVICE_VERSION: "1.0.0",
                DEPLOYMENT_ENVIRONMENT: settings.environment,
                "service.namespace": "context-memory",
            }
        )

        sampler = ParentBased(root=TraceIdRatioBased(0.1 if settings.environment == "production" else 1.0))

        provider = TracerProvider(
            resource=resource,
            sampler=sampler,
        )

        if settings.otlp_exporter_endpoint:
            otlp_exporter = OTLPSpanExporter(
                endpoint=settings.otlp_exporter_endpoint,
                insecure=True,
                timeout=10.0,
            )
            processor = BatchSpanProcessor(
                otlp_exporter,
                max_queue_size=2048,
                max_export_batch_size=512,
                schedule_delay_millis=5000,
                export_timeout_millis=30000,
            )
            provider.add_span_processor(processor)

        trace.set_tracer_provider(provider)
        RedisInstrumentor().instrument(tracer_provider=provider)
        SQLAlchemyInstrumentor().instrument(
            tracer_provider=provider,
            enable_commenter=True,
            commenter_options={},
        )

        logger.info(
            "OpenTelemetry tracing configured",
            service_name=settings.otlp_service_name,
            environment=settings.environment,
            exporter_endpoint=settings.otlp_exporter_endpoint,
        )
        return provider
    except Exception as e:
        logger.error("Failed to configure OpenTelemetry tracing", error=str(e))
        return None


def get_tracer(name: str = "context-memory") -> trace.Tracer:
    """Get a tracer instance for manual instrumentation."""
    return trace.get_tracer(name)
