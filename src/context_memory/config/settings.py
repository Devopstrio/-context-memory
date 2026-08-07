"""Application settings using Pydantic Settings with environment variable loading."""

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="forbid",
        validate_default=True,
    )

    environment: str = Field(default="development", description="Deployment environment")
    port: int = Field(default=8000, ge=1024, le=65535, description="Application port")
    host: str = Field(default="0.0.0.0", description="Application host")
    log_level: str = Field(default="INFO", description="Logging level")
    debug: bool = Field(default=False, description="Debug mode")

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/context_memory",
        description="Async database connection URL",
    )
    database_pool_size: int = Field(default=20, ge=5, le=100, description="Database connection pool size")
    database_max_overflow: int = Field(default=10, ge=0, le=50, description="Database max overflow connections")
    database_pool_timeout: int = Field(default=30, ge=5, le=120, description="Database pool timeout in seconds")
    database_pool_recycle: int = Field(
        default=3600, ge=60, le=7200, description="Database pool recycle time in seconds"
    )
    database_echo: bool = Field(default=False, description="SQL query logging (disable in production)")

    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")
    redis_pool_size: int = Field(default=10, ge=5, le=100, description="Redis connection pool size")
    redis_socket_timeout: float = Field(default=5.0, ge=1.0, le=30.0, description="Redis socket timeout in seconds")
    redis_socket_connect_timeout: float = Field(
        default=5.0, ge=1.0, le=30.0, description="Redis socket connect timeout"
    )
    redis_retry_on_timeout: bool = Field(default=True, description="Retry on Redis timeout")
    redis_ssl: bool = Field(default=False, description="Enable Redis SSL/TLS")

    jwt_secret_key: SecretStr = Field(
        default=SecretStr("super-secret-enterprise-jwt-key-32bytes-minimum"),
        description="JWT signing secret key",
        min_length=32,
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_issuer: str = Field(default="https://auth.enterprise.internal", description="JWT token issuer")
    jwt_audience: str = Field(default="context-memory-api", description="JWT token audience")
    jwt_access_token_expire_minutes: int = Field(
        default=30, ge=5, le=1440, description="JWT access token expiration in minutes"
    )
    jwt_refresh_token_expire_days: int = Field(
        default=7, ge=1, le=30, description="JWT refresh token expiration in days"
    )

    encryption_key: SecretStr = Field(
        default=SecretStr("context-memory-encryption-key-32bytes-here"),
        description="Data encryption key",
        min_length=32,
    )

    otlp_exporter_endpoint: str | None = Field(default=None, description="OpenTelemetry OTLP exporter endpoint")
    otlp_service_name: str = Field(default="context-memory", description="OpenTelemetry service name")
    otlp_enabled: bool = Field(default=False, description="Enable OpenTelemetry tracing")

    max_memories_per_tenant: int = Field(default=100000, ge=1000, description="Maximum memories per tenant")
    max_sessions_per_tenant: int = Field(default=10000, ge=100, description="Maximum sessions per tenant")
    default_retention_days: int = Field(default=90, ge=1, le=3650, description="Default memory retention in days")
    max_batch_size: int = Field(default=100, ge=1, le=1000, description="Maximum batch operation size")

    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_requests_per_minute: int = Field(default=1000, ge=10, description="Rate limit requests per minute")

    cors_origins: list[str] = Field(default=["*"], description="Allowed CORS origins")

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith(("postgresql+asyncpg://", "postgresql://")):
            raise ValueError("Database URL must be a PostgreSQL connection string")
        return v

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, v: str) -> str:
        if not v.startswith(("redis://", "rediss://")):
            raise ValueError("Redis URL must start with redis:// or rediss://")
        return v

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production", "test"}
        if v not in allowed:
            raise ValueError(f"Environment must be one of {allowed}")
        return v

    def get_jwt_secret(self) -> str:
        return self.jwt_secret_key.get_secret_value()

    def get_encryption_key(self) -> str:
        return self.encryption_key.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()
