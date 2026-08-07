"""Tenant Isolation Guardrail with comprehensive security checks."""

import hashlib
import hmac
from typing import Any

import structlog

from context_memory.security.jwt_auth import TokenPayload

logger = structlog.get_logger(__name__)


class SecurityBoundaryViolation(Exception):
    """Exception raised when a cross-tenant boundary violation is detected."""

    def __init__(self, message: str, code: str = "ERR-4001", details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class TenantIsolationGuard:
    """Verifies multi-tenancy isolation boundaries and cryptographic tenant tags."""

    def __init__(self, tenant_signing_key: str = "tenant-isolation-signing-key") -> None:
        self.signing_key = tenant_signing_key

    def verify_tenant_boundary(
        self,
        header_tenant_id: str,
        jwt_claims: TokenPayload,
        request_body_tenant_id: str | None = None,
    ) -> None:
        """Ensure X-Tenant-ID header strictly matches tenant_id in validated JWT claims."""
        if not header_tenant_id:
            raise SecurityBoundaryViolation(
                "Missing required X-Tenant-ID header",
                code="ERR-4001",
                details={"missing_header": "X-Tenant-ID"},
            )

        if not jwt_claims.tenant_id:
            raise SecurityBoundaryViolation(
                "JWT claims missing tenant_id",
                code="ERR-4001",
            )

        if header_tenant_id != jwt_claims.tenant_id:
            msg = (
                f"Tenant boundary violation: Header '{header_tenant_id}' "
                f"does not match authenticated token claim '{jwt_claims.tenant_id}'"
            )
            logger.warning(
                "Tenant boundary violation detected",
                header_tenant=header_tenant_id,
                token_tenant=jwt_claims.tenant_id,
            )
            raise SecurityBoundaryViolation(
                msg,
                code="ERR-4001",
                details={
                    "header_tenant": header_tenant_id,
                    "token_tenant": jwt_claims.tenant_id,
                },
            )

        if request_body_tenant_id and request_body_tenant_id != jwt_claims.tenant_id:
            msg = (
                f"Tenant boundary violation: Request body tenant '{request_body_tenant_id}' "
                f"does not match authenticated token claim '{jwt_claims.tenant_id}'"
            )
            logger.warning(
                "Tenant boundary violation in request body",
                body_tenant=request_body_tenant_id,
                token_tenant=jwt_claims.tenant_id,
            )
            raise SecurityBoundaryViolation(
                msg,
                code="ERR-4001",
                details={
                    "body_tenant": request_body_tenant_id,
                    "token_tenant": jwt_claims.tenant_id,
                },
            )

    def verify_tenant_status(self, tenant_status: str) -> None:
        """Verify tenant is in active status."""
        if tenant_status == "suspended":
            raise SecurityBoundaryViolation("Tenant account is suspended", code="ERR-4002")
        elif tenant_status == "deleted":
            raise SecurityBoundaryViolation("Tenant account has been deleted", code="ERR-4002")
        elif tenant_status != "active":
            raise SecurityBoundaryViolation(f"Tenant account is in invalid state: {tenant_status}", code="ERR-4002")

    def enforce_data_residency(
        self,
        tenant_claims: TokenPayload,
        target_regions: list[str],
        operation: str = "read",
    ) -> None:
        """Validate that target regions comply with tenant's data residency policies."""
        if not tenant_claims.data_residency:
            return

        allowed_set = set(tenant_claims.data_residency)
        for region in target_regions:
            if region not in allowed_set:
                msg = (
                    f"Data residency policy violation: Target region '{region}' "
                    f"is not authorized for tenant '{tenant_claims.tenant_id}' "
                    f"(Allowed: {tenant_claims.data_residency})"
                )
                logger.warning(
                    "Data residency violation",
                    tenant_id=tenant_claims.tenant_id,
                    target_region=region,
                    allowed_regions=tenant_claims.data_residency,
                )
                raise SecurityBoundaryViolation(
                    msg,
                    code="ERR-4003",
                    details={
                        "target_region": region,
                        "allowed_regions": tenant_claims.data_residency,
                    },
                )

    def generate_tenant_tag(self, tenant_id: str) -> str:
        """Generate a cryptographic tag for tenant data isolation."""
        return hmac.new(
            self.signing_key.encode(),
            tenant_id.encode(),
            hashlib.sha256,
        ).hexdigest()

    def verify_tenant_tag(self, tenant_id: str, tag: str) -> bool:
        """Verify a cryptographic tenant tag."""
        expected_tag = self.generate_tenant_tag(tenant_id)
        return hmac.compare_digest(expected_tag, tag)

    def validate_cross_tenant_access(
        self,
        source_tenant: str,
        target_tenant: str,
        access_token: str | None = None,
    ) -> None:
        """Validate cross-tenant access with explicit authorization."""
        if source_tenant != target_tenant:
            if not access_token:
                raise SecurityBoundaryViolation(
                    "Cross-tenant access requires explicit authorization token",
                    code="ERR-4004",
                    details={
                        "source_tenant": source_tenant,
                        "target_tenant": target_tenant,
                    },
                )
            expected_token = self.generate_tenant_tag(f"{source_tenant}:{target_tenant}")
            if not hmac.compare_digest(expected_token, access_token):
                raise SecurityBoundaryViolation(
                    f"Invalid cross-tenant access token from '{source_tenant}' to '{target_tenant}'",
                    code="ERR-4004",
                    details={
                        "source_tenant": source_tenant,
                        "target_tenant": target_tenant,
                    },
                )
