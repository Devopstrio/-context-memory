"""Telemetry: OpenTelemetry and Prometheus."""
from .metrics import REQUEST_COUNT, REQUEST_LATENCY, setup_metrics
from .tracing import get_tracer, setup_tracing

__all__ = [
    "setup_tracing",
    "get_tracer",
    "setup_metrics",
    "REQUEST_COUNT",
    "REQUEST_LATENCY",
]
