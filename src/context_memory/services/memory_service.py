"""Memory service layer with business logic and orchestration."""

import hashlib
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from context_memory.embeddings.embedder import Embedder
from context_memory.governance.retention import RetentionPolicy
from context_memory.models.memory import Memory, MemoryEmbedding
from context_memory.persistence.memory_repo import MemoryRepository
from context_memory.utils.exceptions import (
    AppException,
    ErrorCode,
    ResourceNotFoundError,
    ValidationError,
)

logger = structlog.get_logger(__name__)


class MemoryService:
    """Service layer for memory management with business logic."""

    def __init__(
        self,
        memory_repo: MemoryRepository,
        embedder: Embedder,
        retention_policy: RetentionPolicy,
    ) -> None:
        self.repo = memory_repo
        self.embedder = embedder
        self.retention = retention_policy

    @retry(
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        stop=stop_after_attempt(3),
    )
    async def add_memory(
        self,
        tenant_id: str,
        session_id: str,
        user_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        importance: float = 1.0,
        memory_type: str = "general",
        ttl_days: int | None = None,
    ) -> Memory:
        """Add a new memory with embedding generation."""
        try:
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            memory = Memory(
                tenant_id=tenant_id,
                session_id=session_id,
                user_id=user_id,
                content=content,
                content_hash=content_hash,
                metadata_=metadata or {},
                importance=min(max(importance, 0.0), 10.0),
                memory_type=memory_type,
            )

            if ttl_days is not None:
                memory.expires_at = datetime.now(UTC) + timedelta(days=ttl_days)
            else:
                memory = self.retention.apply_policy(memory)

            memory = await self.repo.create(memory)

            try:
                embedding_vector = await self.embedder.embed(content)
                embedding = MemoryEmbedding(
                    memory_id=memory.id,
                    embedding_vector=embedding_vector,
                    model_name=self.embedder.model_name,
                    dimensions=len(embedding_vector),
                    model_version=self.embedder.model_version,
                    checksum=hashlib.sha256(str(embedding_vector).encode()).hexdigest(),
                )
                await self.repo.create_embedding(embedding)
            except Exception as e:
                logger.error(
                    "Failed to generate embedding, memory created without embedding",
                    memory_id=str(memory.id),
                    error=str(e),
                )

            logger.info(
                "Memory added successfully",
                memory_id=str(memory.id),
                tenant_id=tenant_id,
                session_id=session_id,
                memory_type=memory_type,
            )
            return memory
        except Exception as e:
            logger.error(
                "Failed to add memory",
                tenant_id=tenant_id,
                session_id=session_id,
                error=str(e),
                exc_info=True,
            )
            raise AppException(
                message="Failed to create memory",
                error_code=ErrorCode.INTERNAL_ERROR,
                details={"original_error": str(e)},
            ) from e

    async def get_memory(self, memory_id: uuid.UUID, tenant_id: str) -> Memory | None:
        """Retrieve a memory by ID with tenant isolation."""
        memory = await self.repo.get_by_id(memory_id, tenant_id)
        if memory and not self.retention.is_expired(memory):
            await self.repo.record_access(memory_id, tenant_id)
            return memory
        return None

    async def get_session_memories(
        self,
        tenant_id: str,
        session_id: str,
        limit: int = 100,
        offset: int = 0,
        memory_type: str | None = None,
    ) -> Sequence[Memory]:
        """Retrieve memories for a session with filtering."""
        memories = await self.repo.get_by_session(tenant_id, session_id, limit, offset)
        if memory_type:
            memories = [m for m in memories if m.memory_type == memory_type]
        return [m for m in memories if not self.retention.is_expired(m)]

    async def count_session_memories(self, tenant_id: str, session_id: str) -> int:
        """Count memories in a session."""
        memories = await self.repo.get_by_session(tenant_id, session_id, limit=10000)
        return len([m for m in memories if not self.retention.is_expired(m)])

    async def update_memory(
        self,
        memory_id: uuid.UUID,
        tenant_id: str,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
        importance: float | None = None,
    ) -> Memory | None:
        """Update a memory with validation."""
        if importance is not None and not (0.0 <= importance <= 10.0):
            raise ValidationError(
                "Importance must be between 0.0 and 10.0",
                details={"provided_value": importance},
            )

        memory = await self.repo.update(
            memory_id=memory_id,
            tenant_id=tenant_id,
            content=content,
            metadata=metadata,
            importance=importance,
        )

        if content and memory:
            try:
                embedding_vector = await self.embedder.embed(content)
                embedding = MemoryEmbedding(
                    memory_id=memory.id,
                    embedding_vector=embedding_vector,
                    model_name=self.embedder.model_name,
                    dimensions=len(embedding_vector),
                    model_version=self.embedder.model_version,
                    checksum=hashlib.sha256(str(embedding_vector).encode()).hexdigest(),
                )
                await self.repo.create_embedding(embedding)
            except Exception as e:
                logger.error(
                    "Failed to update embedding",
                    memory_id=str(memory_id),
                    error=str(e),
                )

        return memory

    async def delete_memory(self, memory_id: uuid.UUID, tenant_id: str) -> bool:
        """Soft delete a memory."""
        deleted = await self.repo.soft_delete(memory_id, tenant_id)
        if not deleted:
            raise ResourceNotFoundError(
                f"Memory {memory_id} not found",
                resource_type="memory",
            )
        logger.info(
            "Memory deleted",
            memory_id=str(memory_id),
            tenant_id=tenant_id,
        )
        return True

    async def search_similar(
        self,
        tenant_id: str,
        query: str,
        top_k: int = 10,
        memory_type: str | None = None,
    ) -> Sequence[tuple[Memory, float]]:
        """Search for similar memories using semantic similarity."""
        try:
            query_embedding = await self.embedder.embed(query)
            results = await self.repo.search_similar(
                tenant_id=tenant_id,
                query_embedding=query_embedding,
                top_k=top_k,
                memory_type=memory_type,
            )
            active_results = [(mem, score) for mem, score in results if not self.retention.is_expired(mem)]
            logger.info(
                "Similarity search completed",
                tenant_id=tenant_id,
                query_length=len(query),
                results_count=len(active_results),
            )
            return active_results
        except Exception as e:
            logger.error(
                "Failed to search similar memories",
                tenant_id=tenant_id,
                error=str(e),
                exc_info=True,
            )
            raise AppException(
                message="Failed to search memories",
                error_code=ErrorCode.INTERNAL_ERROR,
                details={"original_error": str(e)},
            ) from e

    async def batch_create(
        self,
        memories_data: list[dict[str, Any]],
        tenant_id: str,
    ) -> list[Memory]:
        """Create multiple memories in batch."""
        results = []
        errors = []
        for i, data in enumerate(memories_data):
            try:
                memory = await self.add_memory(
                    tenant_id=tenant_id,
                    session_id=data["session_id"],
                    user_id=data["user_id"],
                    content=data["content"],
                    metadata=data.get("metadata", {}),
                    importance=data.get("importance", 1.0),
                    memory_type=data.get("memory_type", "general"),
                )
                results.append(memory)
            except Exception as e:
                errors.append({"index": i, "error": str(e)})
                logger.error(
                    "Batch memory creation failed for item",
                    index=i,
                    error=str(e),
                )

        if errors and not results:
            raise AppException(
                message="Batch memory creation failed",
                error_code=ErrorCode.VALIDATION_ERROR,
                details={"errors": errors},
            )

        logger.info(
            "Batch memory creation completed",
            tenant_id=tenant_id,
            success_count=len(results),
            error_count=len(errors),
        )
        return results

    async def cleanup_expired_memories(self, tenant_id: str) -> int:
        """Clean up expired memories for a tenant."""
        cleaned = await self.repo.cleanup_expired(tenant_id)
        logger.info(
            "Expired memory cleanup completed",
            tenant_id=tenant_id,
            cleaned_count=cleaned,
        )
        return cleaned
