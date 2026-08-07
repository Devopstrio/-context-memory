"""JWT Authentication and Claims Validation with production-grade security."""

import time
from typing import Any

import jwt
import structlog
from pydantic import BaseModel, Field, field_validator

from context_memory.config.settings import get_settings

logger = structlog.get_logger(__name__)


class TokenPayload(BaseModel):
    """JWT token payload with all required claims."""

    iss: str
    sub: str
    aud: str
    exp: int
    iat: int
    jti: str
    tenant_id: str
    roles: list[str] = Field(default_factory=lambda: ["context:read"])
    data_residency: list[str] = Field(default_factory=lambda: ["EU", "US"])
    token_type: str = Field(default="access")

    @field_validator("roles")
    @classmethod
    def validate_roles(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("Roles list cannot be empty")
        return v

    @field_validator("tenant_id")
    @classmethod
    def validate_tenant_id(cls, v: str) -> str:
        if not v or len(v) < 3:
            raise ValueError("Tenant ID must be at least 3 characters")
        return v


class TokenValidationError(Exception):
    """Custom exception for token validation failures."""

    def __init__(self, message: str, code: str = "TOKEN_INVALID") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class TokenExpiredError(TokenValidationError):
    """Exception for expired tokens."""

    def __init__(self) -> None:
        super().__init__("Token has expired", "TOKEN_EXPIRED")


class TokenBlacklistedError(TokenValidationError):
    """Exception for blacklisted tokens."""

    def __init__(self) -> None:
        super().__init__("Token has been revoked", "TOKEN_BLACKLISTED")


class JWTAuthenticator:
    """Enterprise-grade JWT authentication and validation."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._blacklist: set[str] = set()

    def decode_and_validate(
        self,
        token: str,
        verify_exp: bool = True,
        verify_aud: bool = True,
    ) -> TokenPayload:
        """Decode and validate a JWT token with comprehensive checks."""
        if not token:
            raise TokenValidationError("Token is required", "TOKEN_MISSING")

        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                self.settings.get_jwt_secret(),
                algorithms=[self.settings.jwt_algorithm],
                options={
                    "verify_signature": True,
                    "verify_exp": verify_exp,
                    "verify_aud": verify_aud,
                    "verify_iss": True,
                    "verify_iat": True,
                    "require": ["exp", "iat", "jti", "sub", "tenant_id"],
                },
                audience=self.settings.jwt_audience,
                issuer=self.settings.jwt_issuer,
                leeway=30,
            )

            if payload.get("jti") in self._blacklist:
                raise TokenBlacklistedError()

            if payload.get("token_type") not in ("access", "refresh"):
                raise TokenValidationError("Invalid token type", "TOKEN_TYPE_INVALID")

            return TokenPayload(**payload)
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            raise TokenExpiredError()
        except jwt.InvalidTokenError as e:
            logger.warning("Invalid token", error=str(e))
            raise TokenValidationError(f"Invalid token: {str(e)}", "TOKEN_INVALID")
        except Exception as e:
            logger.error("Token validation error", error=str(e))
            raise TokenValidationError("Token validation failed", "TOKEN_ERROR")

    def create_access_token(
        self,
        tenant_id: str,
        sub: str = "service-agent",
        roles: list[str] | None = None,
        data_residency: list[str] | None = None,
        expires_in_minutes: int | None = None,
        jti: str | None = None,
    ) -> str:
        """Create a signed JWT access token."""
        import uuid

        now = int(time.time())
        expire_minutes = expires_in_minutes or self.settings.jwt_access_token_expire_minutes

        claims = {
            "iss": self.settings.jwt_issuer,
            "sub": sub,
            "aud": self.settings.jwt_audience,
            "exp": now + (expire_minutes * 60),
            "iat": now,
            "nbf": now,
            "jti": jti or str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "roles": roles or ["context:read"],
            "data_residency": data_residency or ["EU", "US"],
            "token_type": "access",
        }

        token = jwt.encode(
            claims,
            self.settings.get_jwt_secret(),
            algorithm=self.settings.jwt_algorithm,
        )

        logger.info(
            "Access token created",
            tenant_id=tenant_id,
            sub=sub,
            expires_in=expire_minutes,
        )
        return token

    def create_refresh_token(
        self,
        tenant_id: str,
        sub: str = "service-agent",
        expires_in_days: int | None = None,
    ) -> str:
        """Create a signed JWT refresh token."""
        import uuid

        now = int(time.time())
        expire_days = expires_in_days or self.settings.jwt_refresh_token_expire_days

        claims = {
            "iss": self.settings.jwt_issuer,
            "sub": sub,
            "aud": self.settings.jwt_audience,
            "exp": now + (expire_days * 86400),
            "iat": now,
            "nbf": now,
            "jti": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "roles": ["refresh"],
            "data_residency": ["EU", "US"],
            "token_type": "refresh",
        }

        token = jwt.encode(
            claims,
            self.settings.get_jwt_secret(),
            algorithm=self.settings.jwt_algorithm,
        )

        logger.info(
            "Refresh token created",
            tenant_id=tenant_id,
            sub=sub,
            expires_in_days=expire_days,
        )
        return token

    def blacklist_token(self, jti: str) -> None:
        """Add a token JTI to the blacklist."""
        self._blacklist.add(jti)
        logger.info("Token blacklisted", jti=jti)

    def is_blacklisted(self, jti: str) -> bool:
        """Check if a token JTI is blacklisted."""
        return jti in self._blacklist

    def generate_test_token(
        self,
        tenant_id: str = "tenant-corp-alpha",
        roles: list[str] | None = None,
        data_residency: list[str] | None = None,
        expires_in_seconds: int = 3600,
    ) -> str:
        """Generate a test token for integration testing."""
        import uuid

        now = int(time.time())

        claims = {
            "iss": self.settings.jwt_issuer,
            "sub": "service-agent-test",
            "aud": self.settings.jwt_audience,
            "exp": now + expires_in_seconds,
            "iat": now,
            "nbf": now,
            "jti": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "roles": roles or ["context:read", "session:read", "memory:write"],
            "data_residency": data_residency or ["EU", "US"],
            "token_type": "access",
        }

        return jwt.encode(
            claims,
            self.settings.get_jwt_secret(),
            algorithm=self.settings.jwt_algorithm,
        )
