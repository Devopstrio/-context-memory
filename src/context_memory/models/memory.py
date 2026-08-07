"""Memory and MemoryEmbedding ORM models."""
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from context_memory.models.base import Base, TimestampMixin, UUIDMixin


class Memory(Base, UUIDMixin, TimestampMixin):
    """Stores contextual memories for LLM sessions."""

    __tablename__ = "memories"

    tenant_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="Multi-tenant identifier"
    )
    session_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True, comment="Session identifier"
    )
    user_id: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="User identifier"
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Memory content text"
    )
    content_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="SHA-256 hash of content for deduplication"
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False, comment="Flexible metadata storage"
    )
    importance: Mapped[float] = mapped_column(
        Float, default=1.0, nullable=False, comment="Memory importance score (0.0-10.0)"
    )
    memory_type: Mapped[str] = mapped_column(
        String(50), default="general", nullable=False, comment="Type of memory (general, factual, episodic, procedural)"
    )
    access_count: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="Number of times this memory was accessed"
    )
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Last time this memory was accessed"
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True, comment="Memory expiration timestamp"
    )
    is_deleted: Mapped[bool] = mapped_column(
        default=False, nullable=False, index=True, comment="Soft delete flag"
    )

    embedding: Mapped[Optional["MemoryEmbedding"]] = relationship(
        "MemoryEmbedding",
        back_populates="memory",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_memories_tenant_session", "tenant_id", "session_id"),
        Index("ix_memories_tenant_type", "tenant_id", "memory_type"),
        Index("ix_memories_tenant_importance", "tenant_id", "importance"),
        Index(
            "ix_memories_tenant_expires",
            "tenant_id",
            "expires_at",
            postgresql_where=("is_deleted = FALSE"),
        ),
        {"comment": "Context memories for LLM applications"},
    )

    def __repr__(self) -> str:
        return f"<Memory(id={self.id}, tenant={self.tenant_id}, type={self.memory_type})>"


class MemoryEmbedding(Base, UUIDMixin):
    """Stores vector embeddings for semantic memory search."""

    __tablename__ = "memory_embeddings"

    memory_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("memories.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
        comment="Reference to the parent memory",
    )
    embedding_vector: Mapped[list[float]] = mapped_column(
        JSONB, nullable=False, comment="Vector embedding array"
    )
    model_name: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Embedding model identifier"
    )
    dimensions: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Embedding vector dimensions"
    )
    model_version: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Embedding model version"
    )
    checksum: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="Checksum of the embedding for integrity validation"
    )

    memory: Mapped["Memory"] = relationship(
        "Memory",
        back_populates="embedding",
        lazy="selectin",
    )

    __table_args__ = (
        Index(
            "ix_memory_embeddings_model",
            "model_name",
            "model_version",
        ),
        {"comment": "Vector embeddings for semantic memory search"},
    )

    def __repr__(self) -> str:
        return f"<MemoryEmbedding(memory_id={self.memory_id}, model={self.model_name})>"
