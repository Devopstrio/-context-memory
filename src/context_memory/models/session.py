"""Session ORM model for context memory sessions."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from context_memory.models.base import Base, TimestampMixin, UUIDMixin


class Session(Base, UUIDMixin, TimestampMixin):
    """Represents a user session with associated context memory."""

    __tablename__ = "sessions"

    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True, comment="Multi-tenant identifier")
    session_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="Unique session identifier"
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, comment="User identifier")
    status: Mapped[str] = mapped_column(
        String(50), default="active", nullable=False, comment="Session status (active, paused, completed, expired)"
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False, comment="Session metadata")
    context_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, comment="Serialized context snapshot for quick restoration"
    )
    memory_count: Mapped[int] = mapped_column(
        default=0, nullable=False, comment="Cached count of memories in this session"
    )
    total_tokens_used: Mapped[int] = mapped_column(
        default=0, nullable=False, comment="Total tokens used in this session"
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
        comment="Last activity timestamp",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True, comment="Session expiration timestamp"
    )
    is_archived: Mapped[bool] = mapped_column(
        default=False, nullable=False, comment="Archive flag for completed sessions"
    )

    __table_args__ = (
        Index("ix_sessions_tenant_session", "tenant_id", "session_id", unique=True),
        Index("ix_sessions_tenant_status", "tenant_id", "status"),
        Index(
            "ix_sessions_expires",
            "expires_at",
            postgresql_where=("is_archived = FALSE"),
        ),
        {"comment": "Context memory sessions"},
    )

    def __repr__(self) -> str:
        return f"<Session(tenant={self.tenant_id}, session={self.session_id}, status={self.status})>"
