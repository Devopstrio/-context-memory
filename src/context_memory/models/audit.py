"""Audit log ORM model for compliance and security tracking."""
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from context_memory.models.base import Base, UUIDMixin


class AuditLog(Base, UUIDMixin):
    """Immutable audit trail for all memory and session operations."""

    __tablename__ = "audit_logs"

    tenant_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="Tenant identifier"
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="User who performed the action"
    )
    action: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True, comment="Action performed (create, read, update, delete)"
    )
    resource_type: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Type of resource (memory, session, tenant)"
    )
    resource_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="Identifier of the affected resource"
    )
    changes: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True, comment="Record of changes made"
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False, comment="Additional audit metadata"
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45), nullable=True, comment="Client IP address"
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Client user agent"
    )
    correlation_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, index=True, comment="Correlation ID for request tracing"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("ix_audit_tenant_action", "tenant_id", "action"),
        Index("ix_audit_created_at", "created_at"),
        {"comment": "Audit log for compliance and security tracking"},
    )

    def __repr__(self) -> str:
        return f"<AuditLog(tenant={self.tenant_id}, action={self.action}, resource={self.resource_type})>"
