"""Tenant ORM model for multi-tenant configuration."""

from typing import Any

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from context_memory.models.base import Base, TimestampMixin, UUIDMixin


class Tenant(Base, UUIDMixin, TimestampMixin):
    """Tenant configuration and settings for multi-tenant isolation."""

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, comment="Tenant name")
    tenant_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True, comment="Unique tenant identifier"
    )
    status: Mapped[str] = mapped_column(
        String(50), default="active", nullable=False, comment="Tenant status (active, suspended, deleted)"
    )
    tier: Mapped[str] = mapped_column(
        String(50), default="standard", nullable=False, comment="Service tier (standard, premium, enterprise)"
    )
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False, comment="Tenant-specific configuration"
    )
    rate_limit: Mapped[int] = mapped_column(Integer, default=1000, nullable=False, comment="API rate limit per minute")
    max_memories: Mapped[int] = mapped_column(
        Integer, default=10000, nullable=False, comment="Maximum memories allowed"
    )
    max_sessions: Mapped[int] = mapped_column(Integer, default=1000, nullable=False, comment="Maximum sessions allowed")
    retention_days: Mapped[int] = mapped_column(
        Integer, default=90, nullable=False, comment="Data retention period in days"
    )
    data_residency: Mapped[str] = mapped_column(
        String(100), default="global", nullable=False, comment="Data residency region"
    )
    encryption_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="Enable data encryption"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, comment="Soft delete flag")

    def __repr__(self) -> str:
        return f"<Tenant(id={self.tenant_id}, name={self.name}, tier={self.tier})>"
