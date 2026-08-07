"""Main FastAPI application entry point for Context Memory System."""
from fastapi import FastAPI

from context_memory.api.routes import router as api_router
from context_memory.config.settings import get_settings
from context_memory.telemetry.metrics import setup_metrics
from context_memory.telemetry.tracing import setup_tracing
from context_memory.utils.exceptions import (
    AppException,
    app_exception_handler,
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from context_memory.utils.logging import setup_logging
from context_memory.utils.middleware import (
    CorrelationIdMiddleware,
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
    TenantContextMiddleware,
)

settings = get_settings()
setup_logging()

app = FastAPI(
    title="Context Memory System",
    description="Enterprise Multi-tenant Context Memory & Retrieval Engine for LLM Applications",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Setup Telemetry
setup_tracing()
setup_metrics(app)

# Register Middlewares
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=settings.rate_limit_requests_per_minute)
app.add_middleware(TenantContextMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CorrelationIdMiddleware)

# Register Exception Handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Include API router
app.include_router(api_router)
