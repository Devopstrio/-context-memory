"""Repository for Tenant database operations."""

from collections.abc import Sequence
from typing import Any

import structlog
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from context_memory.models.tenant import Tenant

logger = structlog.get_logger(__name__)


class TenantRepository:
    """Repository for tenant management operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, tenant: Tenant) -> Tenant:
        """Create a new tenant."""
        self.session.add(tenant)
        await self.session.flush()
        await self.session.refresh(tenant)
        logger.info("Tenant created", tenant_id=tenant.tenant_id, name=tenant.name)
        return tenant

    async def get_by_id(self, tenant_id: str) -> Tenant | None:
        """Retrieve a tenant by tenant_id."""
        result = await self.session.execute(
            select(Tenant).where(and_(Tenant.tenant_id == tenant_id, Tenant.is_deleted.is_(False)))
        )
        return result.scalar_one_or_none()

    async def get_active_tenants(self, limit: int = 100, offset: int = 0) -> Sequence[Tenant]:
        """Retrieve all active tenants."""
        result = await self.session.execute(
            select(Tenant)
            .where(and_(Tenant.status == "active", Tenant.is_deleted.is_(False)))
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def update_settings(self, tenant_id: str, settings: dict[str, Any]) -> Tenant | None:
        """Update tenant settings."""
        stmt = (
            update(Tenant)
            .where(and_(Tenant.tenant_id == tenant_id, Tenant.is_deleted.is_(False)))
            .values(settings=settings)
            .returning(Tenant)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.scalar_one_or_none()

    async def update_status(self, tenant_id: str, status: str) -> Tenant | None:
        """Update tenant status."""
        stmt = (
            update(Tenant)
            .where(and_(Tenant.tenant_id == tenant_id, Tenant.is_deleted.is_(False)))
            .values(status=status)
            .returning(Tenant)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.scalar_one_or_none()

    async def soft_delete(self, tenant_id: str) -> bool:
        """Soft delete a tenant."""
        stmt = (
            update(Tenant)
            .where(and_(Tenant.tenant_id == tenant_id, Tenant.is_deleted.is_(False)))
            .values(is_deleted=True, status="deleted")
            .returning(Tenant.id)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return len(result.scalars().all()) > 0
