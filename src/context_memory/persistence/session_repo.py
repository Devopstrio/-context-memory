"""Repository for Session database operations."""

from collections.abc import Sequence
from datetime import UTC, datetime

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from context_memory.models.session import Session

logger = structlog.get_logger(__name__)


class SessionRepository:
    """Repository for session management operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(self, session: Session) -> Session:
        """Create or update a session."""
        stmt = (
            insert(Session)
            .values(
                tenant_id=session.tenant_id,
                session_id=session.session_id,
                user_id=session.user_id,
                status=session.status,
                metadata_=session.metadata_,
                last_active_at=datetime.now(UTC),
            )
            .on_conflict_do_update(
                index_elements=["tenant_id", "session_id"],
                set_={
                    "user_id": session.user_id,
                    "status": session.status,
                    "metadata_": session.metadata_,
                    "last_active_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                },
            )
            .returning(Session)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        created_session = result.scalar_one()
        logger.info(
            "Session upserted",
            tenant_id=session.tenant_id,
            session_id=session.session_id,
        )
        return created_session

    async def get(self, tenant_id: str, session_id: str) -> Session | None:
        """Retrieve a session by tenant and session ID."""
        result = await self.session.execute(
            select(Session).where(
                and_(
                    Session.tenant_id == tenant_id,
                    Session.session_id == session_id,
                    Session.is_archived == False,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_active_sessions(self, tenant_id: str, limit: int = 100, offset: int = 0) -> Sequence[Session]:
        """Retrieve active sessions for a tenant."""
        result = await self.session.execute(
            select(Session)
            .where(
                and_(
                    Session.tenant_id == tenant_id,
                    Session.status == "active",
                    Session.is_archived == False,
                )
            )
            .order_by(Session.last_active_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def update_status(self, tenant_id: str, session_id: str, status: str) -> Session | None:
        """Update session status."""
        stmt = (
            update(Session)
            .where(
                and_(
                    Session.tenant_id == tenant_id,
                    Session.session_id == session_id,
                )
            )
            .values(
                status=status,
                updated_at=datetime.now(UTC),
            )
            .returning(Session)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.scalar_one_or_none()

    async def archive(self, tenant_id: str, session_id: str) -> bool:
        """Archive a completed session."""
        stmt = (
            update(Session)
            .where(
                and_(
                    Session.tenant_id == tenant_id,
                    Session.session_id == session_id,
                )
            )
            .values(
                is_archived=True,
                status="archived",
                updated_at=datetime.now(UTC),
            )
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def update_activity(self, tenant_id: str, session_id: str) -> None:
        """Update last active timestamp for a session."""
        stmt = (
            update(Session)
            .where(
                and_(
                    Session.tenant_id == tenant_id,
                    Session.session_id == session_id,
                )
            )
            .values(last_active_at=datetime.now(UTC))
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def count_active_by_tenant(self, tenant_id: str) -> int:
        """Count active sessions for a tenant."""
        result = await self.session.execute(
            select(func.count(Session.id)).where(
                and_(
                    Session.tenant_id == tenant_id,
                    Session.status == "active",
                    Session.is_archived == False,
                )
            )
        )
        return result.scalar_one()

    async def cleanup_expired(self, tenant_id: str) -> int:
        """Archive expired sessions."""
        now = datetime.now(UTC)
        stmt = (
            update(Session)
            .where(
                and_(
                    Session.tenant_id == tenant_id,
                    Session.expires_at.isnot(None),
                    Session.expires_at <= now,
                    Session.is_archived == False,
                )
            )
            .values(is_archived=True, status="expired", updated_at=now)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        count = result.rowcount
        if count > 0:
            logger.info("Cleaned up expired sessions", tenant_id=tenant_id, count=count)
        return count
