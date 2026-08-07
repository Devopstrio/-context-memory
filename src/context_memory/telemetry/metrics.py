"""Prometheus metrics for Context Memory service."""

from fastapi import FastAPI
from prometheus_client import Counter, Gauge, Histogram, Info
from prometheus_fastapi_instrumentator import Instrumentator

NAMESPACE = "context_memory"

REQUEST_COUNT = Counter(
    f"{NAMESPACE}_http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

REQUEST_LATENCY = Histogram(
    f"{NAMESPACE}_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

ACTIVE_REQUESTS = Gauge(
    f"{NAMESPACE}_active_requests",
    "Number of active requests being processed",
)

ERROR_COUNT = Counter(
    f"{NAMESPACE}_errors_total",
    "Total number of errors",
    ["error_type", "endpoint"],
)

MEMORY_OPERATIONS = Counter(
    f"{NAMESPACE}_memory_operations_total",
    "Total memory operations",
    ["operation", "tenant_id"],
)

MEMORY_COUNT = Gauge(
    f"{NAMESPACE}_memories_total",
    "Total number of memories",
    ["tenant_id"],
)

SESSION_COUNT = Gauge(
    f"{NAMESPACE}_sessions_total",
    "Total number of sessions",
    ["tenant_id", "status"],
)

EMBEDDING_LATENCY = Histogram(
    f"{NAMESPACE}_embedding_duration_seconds",
    "Embedding generation latency in seconds",
    ["model"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

EMBEDDING_ERRORS = Counter(
    f"{NAMESPACE}_embedding_errors_total",
    "Total embedding generation errors",
    ["model", "error_type"],
)

CACHE_HITS = Counter(
    f"{NAMESPACE}_cache_hits_total",
    "Total cache hits",
    ["cache_type"],
)

CACHE_MISSES = Counter(
    f"{NAMESPACE}_cache_misses_total",
    "Total cache misses",
    ["cache_type"],
)

DATABASE_CONNECTIONS = Gauge(
    f"{NAMESPACE}_database_connections",
    "Number of active database connections",
)

DATABASE_QUERY_LATENCY = Histogram(
    f"{NAMESPACE}_database_query_duration_seconds",
    "Database query latency in seconds",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

REDIS_CONNECTION_STATUS = Gauge(
    f"{NAMESPACE}_redis_connection_status",
    "Redis connection status (1=connected, 0=disconnected)",
)

CIRCUIT_BREAKER_STATE = Gauge(
    f"{NAMESPACE}_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["service"],
)

RETRY_COUNT = Counter(
    f"{NAMESPACE}_retries_total",
    "Total number of retry attempts",
    ["operation", "attempt"],
)

TENANT_LIMIT_GAUGE = Gauge(
    f"{NAMESPACE}_tenant_limit_usage",
    "Tenant resource usage percentage",
    ["tenant_id", "resource_type"],
)

SERVICE_INFO = Info(
    f"{NAMESPACE}_service_info",
    "Context Memory service information",
)


def setup_metrics(app: FastAPI) -> None:
    """Configure Prometheus metrics instrumentation for FastAPI app."""
    from context_memory.config.settings import get_settings

    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/health/live", "/health/ready", "/health/startup", "/metrics"],
        inprogress_name=f"{NAMESPACE}_http_requests_inprogress",
        inprogress_labels=True,
    ).instrument(app).expose(
        app,
        endpoint="/metrics",
        include_in_schema=True,
    )

    SERVICE_INFO.info(
        {
            "version": "1.0.0",
            "environment": get_settings().environment,
            "python_version": "3.11",
        }
    )
