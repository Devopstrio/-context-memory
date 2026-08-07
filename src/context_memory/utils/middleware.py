"""Production-grade middleware for request processing pipeline."""

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from context_memory.telemetry.metrics import REQUEST_COUNT, REQUEST_LATENCY

logger = structlog.get_logger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Middleware to inject and propagate correlation IDs for request tracing."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        correlation_id = request.headers.get(
            "X-Correlation-ID",
            request.headers.get("X-Request-ID", str(uuid.uuid4())),
        )
        request.state.correlation_id = correlation_id
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            request_id=str(uuid.uuid4()),
        )
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Request-ID"] = getattr(request.state, "request_id", str(uuid.uuid4()))
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for comprehensive request/response logging."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        start_time = time.monotonic()
        request.state.start_time = start_time
        logger.info(
            "Incoming request",
            method=request.method,
            path=request.url.path,
            query_params=str(request.query_params),
            client_host=request.client.host if request.client else "unknown",
            user_agent=request.headers.get("user-agent", "unknown"),
        )
        try:
            response = await call_next(request)
            duration_ms = (time.monotonic() - start_time) * 1000
            request.state.duration_ms = duration_ms

            REQUEST_COUNT.labels(
                method=request.method,
                endpoint=request.url.path,
                status_code=str(response.status_code),
            ).inc()

            REQUEST_LATENCY.labels(
                method=request.method,
                endpoint=request.url.path,
            ).observe(duration_ms / 1000)

            response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
            logger.info(
                "Request completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=f"{duration_ms:.2f}",
            )
            return response
        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            logger.error(
                "Request failed",
                method=request.method,
                path=request.url.path,
                error=str(e),
                duration_ms=f"{duration_ms:.2f}",
                exc_info=True,
            )
            raise


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Middleware to extract and validate tenant context from requests."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        tenant_id = request.headers.get("X-Tenant-ID")
        if tenant_id:
            request.state.tenant_id = tenant_id
            structlog.contextvars.bind_contextvars(tenant_id=tenant_id)
        response = await call_next(request)
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware for rate limiting based on tenant ID."""

    def __init__(self, app: ASGIApp, requests_per_minute: int = 1000) -> None:
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self._request_counts: dict[str, list[float]] = {}

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        from fastapi.responses import JSONResponse

        tenant_id = getattr(request.state, "tenant_id", "anonymous")
        current_time = time.time()

        if tenant_id not in self._request_counts:
            self._request_counts[tenant_id] = []

        window_start = current_time - 60
        self._request_counts[tenant_id] = [t for t in self._request_counts[tenant_id] if t > window_start]

        if len(self._request_counts[tenant_id]) >= self.requests_per_minute:
            logger.warning(
                "Rate limit exceeded",
                tenant_id=tenant_id,
                count=len(self._request_counts[tenant_id]),
                limit=self.requests_per_minute,
            )
            from context_memory.utils.exceptions import ErrorCode, ErrorResponse

            return JSONResponse(
                status_code=429,
                content=ErrorResponse(
                    error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
                    message="Rate limit exceeded. Please retry after 60 seconds.",
                    correlation_id=getattr(request.state, "correlation_id", None),
                ).model_dump(),
            )

        self._request_counts[tenant_id].append(current_time)
        response = await call_next(request)

        remaining = self.requests_per_minute - len(self._request_counts[tenant_id])
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        response.headers["X-RateLimit-Reset"] = str(int(current_time + 60))
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, proxy-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response
