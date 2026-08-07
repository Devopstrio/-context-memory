"""Role-Based (RBAC) and Attribute-Based (ABAC) Access Control Engine."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import structlog

from context_memory.security.jwt_auth import TokenPayload
from context_memory.security.tenant_guard import SecurityBoundaryViolation

logger = structlog.get_logger(__name__)


class Permission(str, Enum):
    """Granular permissions for access control."""

    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"
    MEMORY_DELETE = "memory:delete"
    MEMORY_SEARCH = "memory:search"
    MEMORY_ADMIN = "memory:admin"

    SESSION_READ = "session:read"
    SESSION_WRITE = "session:write"
    SESSION_DELETE = "session:delete"
    SESSION_ADMIN = "session:admin"

    TENANT_READ = "tenant:read"
    TENANT_WRITE = "tenant:write"
    TENANT_ADMIN = "tenant:admin"

    AUDIT_READ = "audit:read"
    ADMIN_FULL = "admin:*"


class Role(str, Enum):
    """Predefined roles with permission sets."""

    READER = "reader"
    WRITER = "writer"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"
    SERVICE_ACCOUNT = "service_account"


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.READER: {
        Permission.MEMORY_READ,
        Permission.MEMORY_SEARCH,
        Permission.SESSION_READ,
    },
    Role.WRITER: {
        Permission.MEMORY_READ,
        Permission.MEMORY_WRITE,
        Permission.MEMORY_SEARCH,
        Permission.SESSION_READ,
        Permission.SESSION_WRITE,
    },
    Role.ADMIN: {
        Permission.MEMORY_READ,
        Permission.MEMORY_WRITE,
        Permission.MEMORY_DELETE,
        Permission.MEMORY_SEARCH,
        Permission.MEMORY_ADMIN,
        Permission.SESSION_READ,
        Permission.SESSION_WRITE,
        Permission.SESSION_DELETE,
        Permission.SESSION_ADMIN,
        Permission.TENANT_READ,
        Permission.TENANT_WRITE,
        Permission.AUDIT_READ,
    },
    Role.SUPER_ADMIN: {
        Permission.ADMIN_FULL,
        Permission.MEMORY_ADMIN,
        Permission.SESSION_ADMIN,
        Permission.TENANT_ADMIN,
        Permission.AUDIT_READ,
    },
    Role.SERVICE_ACCOUNT: {
        Permission.MEMORY_READ,
        Permission.MEMORY_WRITE,
        Permission.MEMORY_DELETE,
        Permission.MEMORY_SEARCH,
        Permission.SESSION_READ,
        Permission.SESSION_WRITE,
        Permission.SESSION_DELETE,
    },
}


class RBACABACEngine:
    """Enterprise RBAC and ABAC access control engine."""

    REQUIRED_ROUTE_ROLE = "context:read"
    ADMIN_ROLE = "admin:models"

    @staticmethod
    def get_permissions_for_roles(roles: list[str]) -> set[Permission]:
        """Get all permissions for a set of roles."""
        permissions: set[Permission] = set()
        for role_str in roles:
            try:
                role = Role(role_str)
                permissions.update(ROLE_PERMISSIONS.get(role, set()))
            except ValueError:
                pass
            try:
                perm = Permission(role_str)
                permissions.add(perm)
            except ValueError:
                pass
        return permissions

    def authorize_read_request(
        self,
        claims: TokenPayload,
        request_attributes: Optional[dict[str, Any]] = None,
    ) -> None:
        """Authorize a read request with RBAC and ABAC checks."""
        if not claims.roles:
            raise SecurityBoundaryViolation(
                "Access Denied: Token lacks required roles", code="ERR-4001"
            )

        permissions = self.get_permissions_for_roles(claims.roles)
        if Permission.MEMORY_READ not in permissions and Permission.ADMIN_FULL not in permissions:
            raise SecurityBoundaryViolation(
                "Access Denied: Missing required permission 'memory:read'",
                code="ERR-4001",
            )

        if request_attributes:
            self._evaluate_abac_policies(claims, request_attributes, permissions)

        logger.debug(
            "Read request authorized",
            tenant_id=claims.tenant_id,
            roles=claims.roles,
        )

    def authorize_write_request(
        self,
        claims: TokenPayload,
        request_attributes: Optional[dict[str, Any]] = None,
    ) -> None:
        """Authorize a write request with RBAC and ABAC checks."""
        if not claims.roles:
            raise SecurityBoundaryViolation(
                "Access Denied: Token lacks required roles", code="ERR-4001"
            )

        permissions = self.get_permissions_for_roles(claims.roles)
        if Permission.MEMORY_WRITE not in permissions and Permission.ADMIN_FULL not in permissions:
            raise SecurityBoundaryViolation(
                "Access Denied: Missing required permission 'memory:write'",
                code="ERR-4001",
            )

        if request_attributes:
            self._evaluate_abac_policies(claims, request_attributes, permissions)

        logger.debug(
            "Write request authorized",
            tenant_id=claims.tenant_id,
            roles=claims.roles,
        )

    def authorize_delete_request(
        self,
        claims: TokenPayload,
        request_attributes: Optional[dict[str, Any]] = None,
    ) -> None:
        """Authorize a delete request with RBAC and ABAC checks."""
        if not claims.roles:
            raise SecurityBoundaryViolation(
                "Access Denied: Token lacks required roles", code="ERR-4001"
            )

        permissions = self.get_permissions_for_roles(claims.roles)
        if Permission.MEMORY_DELETE not in permissions and Permission.ADMIN_FULL not in permissions:
            raise SecurityBoundaryViolation(
                "Access Denied: Missing required permission 'memory:delete'",
                code="ERR-4001",
            )

        logger.debug(
            "Delete request authorized",
            tenant_id=claims.tenant_id,
            roles=claims.roles,
        )

    def authorize_admin_request(self, claims: TokenPayload) -> None:
        """Authorize an admin request."""
        permissions = self.get_permissions_for_roles(claims.roles)
        if Permission.ADMIN_FULL not in permissions and Permission.MEMORY_ADMIN not in permissions:
            raise SecurityBoundaryViolation(
                "Access Denied: Action requires administrative privileges",
                code="ERR-4001",
            )

        logger.info(
            "Admin request authorized",
            tenant_id=claims.tenant_id,
            sub=claims.sub,
        )

    def _evaluate_abac_policies(
        self,
        claims: TokenPayload,
        request_attributes: dict[str, Any],
        permissions: set[Permission],
    ) -> None:
        """Evaluate ABAC policies based on request attributes."""
        data_classification = request_attributes.get("data_classification")
        if data_classification == "RESTRICTED_PHI":
            if "phi:access" not in claims.roles and Permission.ADMIN_FULL not in permissions:
                raise SecurityBoundaryViolation(
                    "ABAC Policy Violation: Accessing RESTRICTED_PHI requires 'phi:access' role",
                    code="ERR-4001",
                )

        data_residency = request_attributes.get("data_residency")
        if data_residency and claims.data_residency:
            if data_residency not in claims.data_residency:
                raise SecurityBoundaryViolation(
                    f"ABAC Policy Violation: Data residency '{data_residency}' not in allowed regions",
                    code="ERR-4001",
                )

        time_restricted = request_attributes.get("time_restricted")
        if time_restricted:
            current_hour = datetime.now(timezone.utc).hour
            allowed_hours = request_attributes.get("allowed_hours", [0, 24])
            if not (allowed_hours[0] <= current_hour <= allowed_hours[1]):
                raise SecurityBoundaryViolation(
                    f"ABAC Policy Violation: Access restricted to hours {allowed_hours}",
                    code="ERR-4001",
                )
