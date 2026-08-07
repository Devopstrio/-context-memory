"""Repository for AuditLog database operations."""
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from context_memory.models.audit import AuditLog

logger = structlog.get_logger(__name__)


class AuditRepository:
    """Repository for audit log operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def log(
        self,
        tenant_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        user_id: Optional[str] = None,
        changes: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> AuditLog:
        """Create an audit log entry."""
        audit_entry = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            changes=changes or {},
            metadata_=metadata or {},
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(audit_entry)
        await self.session.flush()
        logger.debug(
            "Audit log created",
            tenant_id=tenant_id,
            action=action,
            resource_type=resource_type,
        )
        return audit_entry

    async def get_by_tenant(
        self,
        tenant_id: str,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[AuditLog]:
        """Retrieve audit logs for a tenant with optional filters."""
        query = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
        if action:
            query = query.where(AuditLog.action == action)
        if resource_type:
            query = query.where(AuditLog.resource_type == resource_type)
        query = query.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_by_correlation_id(self, correlation_id: str) -> Sequence[AuditLog]:
        """Retrieve audit logs by correlation ID."""
        result = await self.session.execute(
            select(AuditLog)
            .where(AuditLog.correlation_id == correlation_id)
            .order_by(AuditLog.created_at.asc())
        )
        return result.scalars().all()

    async def count_by_tenant(self, tenant_id: str) -> int:
        """Count audit logs for a tenant."""
        result = await self.session.execute(
            select(func.count(AuditLog.id)).where(AuditLog.tenant_id == tenant_id)
        )
        return result.scalar_one()
