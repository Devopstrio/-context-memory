"""Repository for Memory and MemoryEmbedding database operations."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

import structlog
from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from context_memory.models.memory import Memory, MemoryEmbedding

logger = structlog.get_logger(__name__)


class MemoryRepository:
    """Repository for memory storage and retrieval operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, memory: Memory) -> Memory:
        """Create a new memory record."""
        self.session.add(memory)
        await self.session.flush()
        await self.session.refresh(memory)
        logger.info(
            "Memory created",
            memory_id=str(memory.id),
            tenant_id=memory.tenant_id,
            session_id=memory.session_id,
        )
        return memory

    async def get_by_id(self, memory_id: uuid.UUID, tenant_id: str) -> Memory | None:
        """Retrieve a memory by ID with tenant isolation."""
        result = await self.session.execute(
            select(Memory).where(
                and_(
                    Memory.id == memory_id,
                    Memory.tenant_id == tenant_id,
                    Memory.is_deleted.is_(False),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_session(
        self, tenant_id: str, session_id: str, limit: int = 100, offset: int = 0
    ) -> Sequence[Memory]:
        """Retrieve all memories for a session."""
        result = await self.session.execute(
            select(Memory)
            .where(
                and_(
                    Memory.tenant_id == tenant_id,
                    Memory.session_id == session_id,
                    Memory.is_deleted.is_(False),
                )
            )
            .order_by(Memory.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_by_tenant(
        self, tenant_id: str, memory_type: str | None = None, limit: int = 100, offset: int = 0
    ) -> Sequence[Memory]:
        """Retrieve memories for a tenant with optional type filter."""
        query = select(Memory).where(and_(Memory.tenant_id == tenant_id, Memory.is_deleted.is_(False)))
        if memory_type:
            query = query.where(Memory.memory_type == memory_type)
        query = query.order_by(Memory.updated_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def update(
        self,
        memory_id: uuid.UUID,
        tenant_id: str,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
        importance: float | None = None,
    ) -> Memory | None:
        """Update a memory's content, metadata, or importance."""
        values: dict[str, Any] = {"updated_at": datetime.now(UTC)}
        if content is not None:
            import hashlib

            values["content"] = content
            values["content_hash"] = hashlib.sha256(content.encode()).hexdigest()
        if metadata is not None:
            values["metadata_"] = metadata
        if importance is not None:
            values["importance"] = importance

        stmt = (
            update(Memory)
            .where(
                and_(
                    Memory.id == memory_id,
                    Memory.tenant_id == tenant_id,
                    Memory.is_deleted.is_(False),
                )
            )
            .values(**values)
            .returning(Memory)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        memory = result.scalar_one_or_none()
        if memory:
            logger.info("Memory updated", memory_id=str(memory_id), tenant_id=tenant_id)
        return memory

    async def soft_delete(self, memory_id: uuid.UUID, tenant_id: str) -> bool:
        """Soft delete a memory by setting is_deleted flag."""
        stmt = (
            update(Memory)
            .where(
                and_(
                    Memory.id == memory_id,
                    Memory.tenant_id == tenant_id,
                    Memory.is_deleted.is_(False),
                )
            )
            .values(
                is_deleted=True,
                updated_at=datetime.now(UTC),
            )
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return bool(result.rowcount > 0)

    async def hard_delete(self, memory_id: uuid.UUID, tenant_id: str) -> bool:
        """Permanently delete a memory record."""
        stmt = delete(Memory).where(and_(Memory.id == memory_id, Memory.tenant_id == tenant_id))
        result = await self.session.execute(stmt)
        await self.session.flush()
        return bool(result.rowcount > 0)

    async def record_access(self, memory_id: uuid.UUID, tenant_id: str) -> None:
        """Record a memory access event."""
        stmt = (
            update(Memory)
            .where(
                and_(
                    Memory.id == memory_id,
                    Memory.tenant_id == tenant_id,
                )
            )
            .values(
                access_count=Memory.access_count + 1,
                last_accessed_at=datetime.now(UTC),
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def count_by_tenant(self, tenant_id: str) -> int:
        """Count total non-deleted memories for a tenant."""
        result = await self.session.execute(
            select(func.count(Memory.id)).where(and_(Memory.tenant_id == tenant_id, Memory.is_deleted.is_(False)))
        )
        return cast(int, result.scalar_one())

    async def create_embedding(self, embedding: MemoryEmbedding) -> MemoryEmbedding:
        """Create or update a memory embedding."""
        stmt = (
            insert(MemoryEmbedding)
            .values(
                memory_id=embedding.memory_id,
                embedding_vector=embedding.embedding_vector,
                model_name=embedding.model_name,
                dimensions=embedding.dimensions,
                model_version=embedding.model_version,
                checksum=embedding.checksum,
            )
            .on_conflict_do_update(
                index_elements=["memory_id"],
                set_={
                    "embedding_vector": embedding.embedding_vector,
                    "model_name": embedding.model_name,
                    "dimensions": embedding.dimensions,
                    "model_version": embedding.model_version,
                    "checksum": embedding.checksum,
                },
            )
            .returning(MemoryEmbedding)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return cast(MemoryEmbedding, result.scalar_one())

    async def get_embedding(self, memory_id: uuid.UUID) -> MemoryEmbedding | None:
        """Retrieve embedding for a memory."""
        result = await self.session.execute(select(MemoryEmbedding).where(MemoryEmbedding.memory_id == memory_id))
        return result.scalar_one_or_none()

    async def search_similar(
        self,
        tenant_id: str,
        query_embedding: list[float],
        top_k: int = 10,
        memory_type: str | None = None,
    ) -> Sequence[tuple[Memory, float]]:
        """Search for similar memories using cosine similarity."""
        query = (
            select(Memory, MemoryEmbedding)
            .join(MemoryEmbedding, Memory.id == MemoryEmbedding.memory_id)
            .where(
                and_(
                    Memory.tenant_id == tenant_id,
                    Memory.is_deleted.is_(False),
                )
            )
        )
        if memory_type:
            query = query.where(Memory.memory_type == memory_type)
        result = await self.session.execute(query)
        rows = result.all()

        scored_results: list[tuple[Memory, float]] = []
        for row in rows:
            memory: Memory = row[0]
            embedding: MemoryEmbedding | None = row[1]
            if embedding and embedding.embedding_vector:
                similarity = self._cosine_similarity(query_embedding, embedding.embedding_vector)
                scored_results.append((memory, similarity))

        scored_results.sort(key=lambda x: x[1], reverse=True)
        return scored_results[:top_k]

    async def cleanup_expired(self, tenant_id: str) -> int:
        """Soft delete expired memories."""
        now = datetime.now(UTC)
        stmt = (
            update(Memory)
            .where(
                and_(
                    Memory.tenant_id == tenant_id,
                    Memory.expires_at.isnot(None),
                    Memory.expires_at <= now,
                    Memory.is_deleted.is_(False),
                )
            )
            .values(is_deleted=True, updated_at=now)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        count = cast(int, result.rowcount)
        if count > 0:
            logger.info("Cleaned up expired memories", tenant_id=tenant_id, count=count)
        return count

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot_product = sum(x * y for x, y in zip(a, b, strict=True))
        norm_a = sum(x**2 for x in a) ** 0.5
        norm_b = sum(y**2 for y in b) ** 0.5
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot_product / (norm_a * norm_b)
