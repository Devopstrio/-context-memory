"""Initial database schema.

Revision ID: 001
Revises: None
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial schema."""
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("tenant_id", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("status", sa.String(50), default="active", nullable=False),
        sa.Column("tier", sa.String(50), default="standard", nullable=False),
        sa.Column("settings", postgresql.JSONB, default=dict, nullable=False),
        sa.Column("rate_limit", sa.Integer, default=1000, nullable=False),
        sa.Column("max_memories", sa.Integer, default=10000, nullable=False),
        sa.Column("max_sessions", sa.Integer, default=1000, nullable=False),
        sa.Column("retention_days", sa.Integer, default=90, nullable=False),
        sa.Column("data_residency", sa.String(100), default="global", nullable=False),
        sa.Column("encryption_enabled", sa.Boolean, default=True, nullable=False),
        sa.Column("is_deleted", sa.Boolean, default=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False, index=True),
        sa.Column("session_id", sa.String(255), nullable=False, index=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), default="active", nullable=False),
        sa.Column("metadata_", postgresql.JSONB, default=dict, nullable=False),
        sa.Column("context_snapshot", postgresql.JSONB, nullable=True),
        sa.Column("memory_count", sa.Integer, default=0, nullable=False),
        sa.Column("total_tokens_used", sa.Integer, default=0, nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("is_archived", sa.Boolean, default=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sessions_tenant_session", "sessions", ["tenant_id", "session_id"], unique=True)
    op.create_index("ix_sessions_tenant_status", "sessions", ["tenant_id", "status"])

    op.create_table(
        "memories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False, index=True),
        sa.Column("session_id", sa.String(255), nullable=False, index=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False, index=True),
        sa.Column("metadata_", postgresql.JSONB, default=dict, nullable=False),
        sa.Column("importance", sa.Float, default=1.0, nullable=False),
        sa.Column("memory_type", sa.String(50), default="general", nullable=False),
        sa.Column("access_count", sa.Integer, default=0, nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("is_deleted", sa.Boolean, default=False, nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_memories_tenant_session", "memories", ["tenant_id", "session_id"])
    op.create_index("ix_memories_tenant_type", "memories", ["tenant_id", "memory_type"])
    op.create_index("ix_memories_tenant_importance", "memories", ["tenant_id", "importance"])

    op.create_table(
        "memory_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("memory_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("memories.id", ondelete="CASCADE"), unique=True, nullable=False, index=True),
        sa.Column("embedding_vector", postgresql.JSONB, nullable=False),
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column("dimensions", sa.Integer, nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_memory_embeddings_model", "memory_embeddings", ["model_name", "model_version"])

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False, index=True),
        sa.Column("user_id", sa.String(255), nullable=True),
        sa.Column("action", sa.String(100), nullable=False, index=True),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=False, index=True),
        sa.Column("changes", postgresql.JSONB, nullable=True),
        sa.Column("metadata_", postgresql.JSONB, default=dict, nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("correlation_id", sa.String(255), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
    )
    op.create_index("ix_audit_tenant_action", "audit_logs", ["tenant_id", "action"])


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table("audit_logs")
    op.drop_table("memory_embeddings")
    op.drop_table("memories")
    op.drop_table("sessions")
    op.drop_table("tenants")
