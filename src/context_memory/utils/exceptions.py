"""Centralized exception handling and error responses."""
from enum import Enum
from typing import Any, Optional

from fastapi import Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ErrorCode(str, Enum):
    """Standardized error codes for the Context Memory service."""

    AUTHENTICATION_FAILED = "AUTH_001"
    TOKEN_EXPIRED = "AUTH_002"
    TOKEN_INVALID = "AUTH_003"
    TOKEN_BLACKLISTED = "AUTH_004"
    INSUFFICIENT_PERMISSIONS = "AUTH_005"

    TENANT_ISOLATION_VIOLATION = "TENANT_001"
    TENANT_NOT_FOUND = "TENANT_002"
    TENANT_SUSPENDED = "TENANT_003"
    TENANT_LIMIT_EXCEEDED = "TENANT_004"

    RESOURCE_NOT_FOUND = "RES_001"
    RESOURCE_ALREADY_EXISTS = "RES_002"
    RESOURCE_CONFLICT = "RES_003"

    VALIDATION_ERROR = "VAL_001"
    INVALID_REQUEST = "VAL_002"
    REQUEST_TOO_LARGE = "VAL_003"

    RATE_LIMIT_EXCEEDED = "RATE_001"

    INTERNAL_ERROR = "INT_001"
    DATABASE_ERROR = "INT_002"
    CACHE_ERROR = "INT_003"
    EMBEDDING_ERROR = "INT_004"
    SERVICE_UNAVAILABLE = "INT_005"


class ErrorResponse(BaseModel):
    """Standardized error response model."""

    error_code: ErrorCode
    message: str
    details: Optional[dict[str, Any]] = Field(default=None, description="Additional error details")
    correlation_id: Optional[str] = Field(default=None, description="Request correlation ID")
    timestamp: str = Field(
        default_factory=lambda: __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    )


class AppException(Exception):
    """Base application exception with error code."""

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        details: Optional[dict[str, Any]] = None,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    ) -> None:
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.status_code = status_code
        super().__init__(message)


class AuthenticationError(AppException):
    """Authentication related errors."""

    def __init__(
        self, message: str, error_code: ErrorCode = ErrorCode.AUTHENTICATION_FAILED
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class AuthorizationError(AppException):
    """Authorization related errors."""

    def __init__(
        self, message: str, error_code: ErrorCode = ErrorCode.INSUFFICIENT_PERMISSIONS
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status.HTTP_403_FORBIDDEN,
        )


class TenantError(AppException):
    """Tenant related errors."""

    def __init__(
        self, message: str, error_code: ErrorCode = ErrorCode.TENANT_ISOLATION_VIOLATION
    ) -> None:
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=status.HTTP_403_FORBIDDEN,
        )


class ResourceNotFoundError(AppException):
    """Resource not found errors."""

    def __init__(self, message: str, resource_type: str = "Resource") -> None:
        super().__init__(
            message=message,
            error_code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            details={"resource_type": resource_type},
        )


class ValidationError(AppException):
    """Validation errors."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            error_code=ErrorCode.VALIDATION_ERROR,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


class RateLimitError(AppException):
    """Rate limiting errors."""

    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__(
            message=message,
            error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )


class ServiceUnavailableError(AppException):
    """Service unavailable errors."""

    def __init__(self, message: str = "Service temporarily unavailable") -> None:
        super().__init__(
            message=message,
            error_code=ErrorCode.SERVICE_UNAVAILABLE,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle custom application exceptions."""
    from context_memory.telemetry.metrics import ERROR_COUNT

    ERROR_COUNT.labels(
        error_type=exc.error_code.value,
        endpoint=request.url.path,
    ).inc()

    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
            correlation_id=getattr(request.state, "correlation_id", None),
        ).model_dump(),
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle HTTP exceptions."""
    from fastapi.exceptions import HTTPException

    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error_code=ErrorCode.INVALID_REQUEST,
                message=str(exc.detail),
                correlation_id=getattr(request.state, "correlation_id", None),
            ).model_dump(),
        )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error_code=ErrorCode.INTERNAL_ERROR,
            message="An unexpected error occurred",
            correlation_id=getattr(request.state, "correlation_id", None),
        ).model_dump(),
    )


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle validation exceptions."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            error_code=ErrorCode.VALIDATION_ERROR,
            message=str(exc),
            correlation_id=getattr(request.state, "correlation_id", None),
        ).model_dump(),
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all unhandled exceptions."""
    import structlog

    logger = structlog.get_logger(__name__)
    logger.error(
        "Unhandled exception",
        error=str(exc),
        path=request.url.path,
        method=request.method,
        exc_info=True,
    )

    from context_memory.telemetry.metrics import ERROR_COUNT

    ERROR_COUNT.labels(
        error_type="unhandled",
        endpoint=request.url.path,
    ).inc()

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error_code=ErrorCode.INTERNAL_ERROR,
            message="An unexpected internal error occurred",
            correlation_id=getattr(request.state, "correlation_id", None),
        ).model_dump(),
    )
