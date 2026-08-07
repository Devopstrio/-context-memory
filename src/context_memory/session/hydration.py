"""Session context hydration service."""
from typing import Any
import structlog

from context_memory.services.memory_service import MemoryService
from context_memory.services.session_service import SessionService

logger = structlog.get_logger(__name__)


class SessionHydrator:
    """Hydrates LLM session context within token budget constraints."""

    def __init__(
        self,
        memory_service: MemoryService,
        session_service: SessionService,
    ) -> None:
        self.memory_service = memory_service
        self.session_service = session_service

    async def hydrate(
        self,
        tenant_id: str,
        session_id: str,
        user_id: str,
        max_tokens: int = 4000,
    ) -> dict[str, Any]:
        """Fetch session memories and hydrate context string within max_tokens limit."""
        await self.session_service.ensure_session(
            tenant_id=tenant_id,
            session_id=session_id,
            user_id=user_id,
        )

        memories = await self.memory_service.get_session_memories(
            tenant_id=tenant_id,
            session_id=session_id,
            limit=100,
        )

        context_parts = []
        token_count = 0
        memory_count = 0

        for m in memories:
            estimated_tokens = len(m.content) // 4 + 1
            if token_count + estimated_tokens > max_tokens:
                break
            context_parts.append(m.content)
            token_count += estimated_tokens
            memory_count += 1

        context = "\n".join(context_parts)

        logger.info(
            "Session hydrated",
            tenant_id=tenant_id,
            session_id=session_id,
            token_count=token_count,
            memory_count=memory_count,
        )

        return {
            "session_id": session_id,
            "context": context,
            "token_count": token_count,
            "memory_count": memory_count,
        }
