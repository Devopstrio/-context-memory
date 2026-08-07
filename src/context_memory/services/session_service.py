"""Session service layer with business logic for session management."""
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

import structlog

from context_memory.models.session import Session
from context_memory.persistence.session_repo import SessionRepository
from context_memory.utils.exceptions import AppException, ErrorCode

logger = structlog.get_logger(__name__)


class SessionService:
    """Service layer for session management with business logic."""

    def __init__(self, session_repo: SessionRepository) -> None:
        self.repo = session_repo

    async def ensure_session(
        self,
        tenant_id: str,
        session_id: str,
        user_id: str,
        metadata: Optional[dict[str, Any]] = None,
        expires_in_days: Optional[int] = None,
    ) -> Session:
        """Ensure a session exists, creating if necessary."""
        try:
            session = Session(
                tenant_id=tenant_id,
                session_id=session_id,
                user_id=user_id,
                status="active",
                metadata_=metadata or {},
                last_active_at=datetime.now(timezone.utc),
            )
            session = await self.repo.upsert(session)
            logger.info(
                "Session ensured",
                tenant_id=tenant_id,
                session_id=session_id,
                status=session.status,
            )
            return session
        except Exception as e:
            logger.error(
                "Failed to ensure session",
                tenant_id=tenant_id,
                session_id=session_id,
                error=str(e),
                exc_info=True,
            )
            raise AppException(
                message="Failed to ensure session",
                error_code=ErrorCode.INTERNAL_ERROR,
                details={"original_error": str(e)},
            )

    async def get_session(self, tenant_id: str, session_id: str) -> Optional[Session]:
        """Retrieve a session by ID with expiry check."""
        session = await self.repo.get(tenant_id, session_id)
        if session and session.expires_at and session.expires_at < datetime.now(timezone.utc):
            await self.repo.update_status(tenant_id, session_id, "expired")
            return None
        if session:
            await self.repo.update_activity(tenant_id, session_id)
        return session

    async def get_active_sessions(
        self, tenant_id: str, limit: int = 100, offset: int = 0
    ) -> Sequence[Session]:
        """Retrieve active sessions for a tenant."""
        return await self.repo.get_active_sessions(tenant_id, limit, offset)

    async def complete_session(self, tenant_id: str, session_id: str) -> bool:
        """Mark a session as completed and archive it."""
        await self.repo.update_status(tenant_id, session_id, "completed")
        archived = await self.repo.archive(tenant_id, session_id)
        logger.info(
            "Session completed and archived",
            tenant_id=tenant_id,
            session_id=session_id,
        )
        return archived

    async def pause_session(self, tenant_id: str, session_id: str) -> Optional[Session]:
        """Pause an active session."""
        session = await self.repo.update_status(tenant_id, session_id, "paused")
        if session:
            logger.info(
                "Session paused",
                tenant_id=tenant_id,
                session_id=session_id,
            )
        return session

    async def resume_session(self, tenant_id: str, session_id: str) -> Optional[Session]:
        """Resume a paused session."""
        session = await self.repo.update_status(tenant_id, session_id, "active")
        if session:
            await self.repo.update_activity(tenant_id, session_id)
            logger.info(
                "Session resumed",
                tenant_id=tenant_id,
                session_id=session_id,
            )
        return session

    async def delete_session(self, tenant_id: str, session_id: str) -> bool:
        """Archive and mark a session for deletion."""
        archived = await self.repo.archive(tenant_id, session_id)
        if archived:
            logger.info(
                "Session marked for deletion",
                tenant_id=tenant_id,
                session_id=session_id,
            )
        return archived

    async def count_active_sessions(self, tenant_id: str) -> int:
        """Count active sessions for a tenant."""
        return await self.repo.count_active_by_tenant(tenant_id)

    async def cleanup_expired_sessions(self, tenant_id: str) -> int:
        """Archive expired sessions."""
        cleaned = await self.repo.cleanup_expired(tenant_id)
        logger.info(
            "Expired session cleanup completed",
            tenant_id=tenant_id,
            cleaned_count=cleaned,
        )
        return cleaned

    async def update_session_metadata(
        self,
        tenant_id: str,
        session_id: str,
        metadata: dict[str, Any],
        merge: bool = True,
    ) -> Optional[Session]:
        """Update session metadata."""
        session = await self.repo.get(tenant_id, session_id)
        if not session:
            return None

        if merge:
            current_metadata = session.metadata_ or {}
            current_metadata.update(metadata)
            session.metadata_ = current_metadata
        else:
            session.metadata_ = metadata

        session = await self.repo.upsert(session)
        logger.info(
            "Session metadata updated",
            tenant_id=tenant_id,
            session_id=session_id,
        )
        return session
