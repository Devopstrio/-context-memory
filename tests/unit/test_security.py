"""Unit tests for security module."""

import time

import pytest

from context_memory.security.jwt_auth import (
    TokenExpiredError,
    TokenPayload,
    TokenValidationError,
)
from context_memory.security.rbac_abac import (
    Permission,
    RBACABACEngine,
)
from context_memory.security.tenant_guard import (
    SecurityBoundaryViolation,
    TenantIsolationGuard,
)


class TestJWTAuthenticator:
    """Tests for JWT authentication."""

    def test_create_access_token(self, authenticator):
        """Test access token creation."""
        token = authenticator.create_access_token(
            tenant_id="test-tenant",
            sub="test-user",
        )
        assert isinstance(token, str)
        assert len(token) > 50

        claims = authenticator.decode_and_validate(token)
        assert claims.tenant_id == "test-tenant"
        assert claims.sub == "test-user"
        assert claims.token_type == "access"

    def test_create_refresh_token(self, authenticator):
        """Test refresh token creation."""
        token = authenticator.create_refresh_token(
            tenant_id="test-tenant",
            sub="test-user",
        )
        assert isinstance(token, str)
        claims = authenticator.decode_and_validate(token)
        assert claims.token_type == "refresh"

    def test_decode_valid_token(self, authenticator):
        """Test decoding a valid token."""
        token = authenticator.generate_test_token(tenant_id="test-tenant")
        claims = authenticator.decode_and_validate(token)
        assert claims.tenant_id == "test-tenant"
        assert "context:read" in claims.roles

    def test_decode_empty_token(self, authenticator):
        """Test decoding empty token raises error."""
        with pytest.raises(TokenValidationError):
            authenticator.decode_and_validate("")

    def test_decode_invalid_token(self, authenticator):
        """Test decoding invalid token raises error."""
        with pytest.raises(TokenValidationError):
            authenticator.decode_and_validate("invalid.token.here")

    def test_decode_expired_token(self, authenticator):
        """Test decoding expired token raises error."""
        token = authenticator.generate_test_token(expires_in_seconds=-1)
        with pytest.raises(TokenExpiredError):
            authenticator.decode_and_validate(token)

    def test_decode_wrong_audience(self, authenticator):
        """Test token with wrong audience is rejected."""
        import jwt as pyjwt

        token = pyjwt.encode(
            {
                "iss": authenticator.settings.jwt_issuer,
                "sub": "test",
                "aud": "wrong-audience",
                "exp": int(time.time()) + 3600,
                "iat": int(time.time()),
                "jti": "test-jti",
                "tenant_id": "test-tenant",
                "roles": ["context:read"],
                "data_residency": ["EU"],
                "token_type": "access",
            },
            authenticator.settings.get_jwt_secret(),
            algorithm="HS256",
        )
        with pytest.raises(TokenValidationError):
            authenticator.decode_and_validate(token)

    def test_token_blacklisting(self, authenticator):
        """Test token blacklisting."""
        token = authenticator.generate_test_token()
        claims = authenticator.decode_and_validate(token)
        authenticator.blacklist_token(claims.jti)
        assert authenticator.is_blacklisted(claims.jti)

        with pytest.raises(TokenValidationError):
            authenticator.decode_and_validate(token)


class TestRBACABACEngine:
    """Tests for RBAC/ABAC engine."""

    def test_get_permissions_for_roles(self):
        """Test getting permissions for roles."""
        permissions = RBACABACEngine.get_permissions_for_roles(["reader"])
        assert Permission.MEMORY_READ in permissions
        assert Permission.MEMORY_WRITE not in permissions

    def test_get_permissions_for_admin(self):
        """Test getting permissions for admin role."""
        permissions = RBACABACEngine.get_permissions_for_roles(["admin"])
        assert Permission.MEMORY_ADMIN in permissions
        assert Permission.SESSION_ADMIN in permissions

    def test_authorize_read_success(self):
        """Test successful read authorization."""
        engine = RBACABACEngine()
        claims = TokenPayload(
            iss="test",
            sub="test",
            aud="test",
            exp=int(time.time()) + 3600,
            iat=int(time.time()),
            jti="test",
            tenant_id="test-tenant",
            roles=["reader"],
            data_residency=["EU"],
            token_type="access",
        )
        engine.authorize_read_request(claims)

    def test_authorize_read_insufficient_permissions(self):
        """Test read authorization with insufficient permissions."""
        engine = RBACABACEngine()
        claims = TokenPayload(
            iss="test",
            sub="test",
            aud="test",
            exp=int(time.time()) + 3600,
            iat=int(time.time()),
            jti="test",
            tenant_id="test-tenant",
            roles=[],
            data_residency=["EU"],
            token_type="access",
        )
        with pytest.raises(SecurityBoundaryViolation):
            engine.authorize_read_request(claims)

    def test_authorize_write_success(self):
        """Test successful write authorization."""
        engine = RBACABACEngine()
        claims = TokenPayload(
            iss="test",
            sub="test",
            aud="test",
            exp=int(time.time()) + 3600,
            iat=int(time.time()),
            jti="test",
            tenant_id="test-tenant",
            roles=["writer"],
            data_residency=["EU"],
            token_type="access",
        )
        engine.authorize_write_request(claims)

    def test_abac_data_classification(self):
        """Test ABAC policy for restricted data."""
        engine = RBACABACEngine()
        claims = TokenPayload(
            iss="test",
            sub="test",
            aud="test",
            exp=int(time.time()) + 3600,
            iat=int(time.time()),
            jti="test",
            tenant_id="test-tenant",
            roles=["reader"],
            data_residency=["EU"],
            token_type="access",
        )
        with pytest.raises(SecurityBoundaryViolation) as exc:
            engine.authorize_read_request(
                claims,
                request_attributes={"data_classification": "RESTRICTED_PHI"},
            )
        assert "phi:access" in str(exc.value)

    def test_abac_data_residency(self):
        """Test ABAC policy for data residency."""
        engine = RBACABACEngine()
        claims = TokenPayload(
            iss="test",
            sub="test",
            aud="test",
            exp=int(time.time()) + 3600,
            iat=int(time.time()),
            jti="test",
            tenant_id="test-tenant",
            roles=["reader"],
            data_residency=["EU"],
            token_type="access",
        )
        with pytest.raises(SecurityBoundaryViolation):
            engine.authorize_read_request(
                claims,
                request_attributes={"data_residency": "APAC"},
            )


class TestTenantIsolationGuard:
    """Tests for tenant isolation guard."""

    def test_verify_tenant_boundary_success(self):
        """Test successful tenant boundary verification."""
        guard = TenantIsolationGuard()
        claims = TokenPayload(
            iss="test",
            sub="test",
            aud="test",
            exp=int(time.time()) + 3600,
            iat=int(time.time()),
            jti="test",
            tenant_id="my-tenant",
            roles=["reader"],
            data_residency=["EU"],
            token_type="access",
        )
        guard.verify_tenant_boundary("my-tenant", claims)

    def test_verify_tenant_boundary_missing_header(self):
        """Test missing tenant header raises error."""
        guard = TenantIsolationGuard()
        claims = TokenPayload(
            iss="test",
            sub="test",
            aud="test",
            exp=int(time.time()) + 3600,
            iat=int(time.time()),
            jti="test",
            tenant_id="my-tenant",
            roles=["reader"],
            data_residency=["EU"],
            token_type="access",
        )
        with pytest.raises(SecurityBoundaryViolation) as exc:
            guard.verify_tenant_boundary("", claims)
        assert "Missing required X-Tenant-ID" in str(exc.value)

    def test_verify_tenant_boundary_mismatch(self):
        """Test tenant mismatch raises error."""
        guard = TenantIsolationGuard()
        claims = TokenPayload(
            iss="test",
            sub="test",
            aud="test",
            exp=int(time.time()) + 3600,
            iat=int(time.time()),
            jti="test",
            tenant_id="my-tenant",
            roles=["reader"],
            data_residency=["EU"],
            token_type="access",
        )
        with pytest.raises(SecurityBoundaryViolation) as exc:
            guard.verify_tenant_boundary("other-tenant", claims)
        assert "Tenant boundary violation" in str(exc.value)

    def test_verify_tenant_status_active(self):
        """Test active tenant status passes."""
        guard = TenantIsolationGuard()
        guard.verify_tenant_status("active")

    def test_verify_tenant_status_suspended(self):
        """Test suspended tenant raises error."""
        guard = TenantIsolationGuard()
        with pytest.raises(SecurityBoundaryViolation) as exc:
            guard.verify_tenant_status("suspended")
        assert "suspended" in str(exc.value).lower()

    def test_enforce_data_residency_success(self):
        """Test data residency check passes."""
        guard = TenantIsolationGuard()
        claims = TokenPayload(
            iss="test",
            sub="test",
            aud="test",
            exp=int(time.time()) + 3600,
            iat=int(time.time()),
            jti="test",
            tenant_id="my-tenant",
            roles=["reader"],
            data_residency=["EU", "US"],
            token_type="access",
        )
        guard.enforce_data_residency(claims, ["EU"])

    def test_enforce_data_residency_violation(self):
        """Test data residency violation raises error."""
        guard = TenantIsolationGuard()
        claims = TokenPayload(
            iss="test",
            sub="test",
            aud="test",
            exp=int(time.time()) + 3600,
            iat=int(time.time()),
            jti="test",
            tenant_id="my-tenant",
            roles=["reader"],
            data_residency=["EU"],
            token_type="access",
        )
        with pytest.raises(SecurityBoundaryViolation):
            guard.enforce_data_residency(claims, ["APAC"])

    def test_tenant_tag_generation(self):
        """Test tenant tag generation and verification."""
        guard = TenantIsolationGuard()
        tag = guard.generate_tenant_tag("my-tenant")
        assert guard.verify_tenant_tag("my-tenant", tag)
        assert not guard.verify_tenant_tag("my-tenant", "invalid-tag")
        assert not guard.verify_tenant_tag("other-tenant", tag)

    def test_cross_tenant_access_validation(self):
        """Test cross-tenant access validation."""
        guard = TenantIsolationGuard()
        access_token = guard.generate_tenant_tag("tenant-a:tenant-b")
        guard.validate_cross_tenant_access("tenant-a", "tenant-b", access_token)
        with pytest.raises(SecurityBoundaryViolation):
            guard.validate_cross_tenant_access("tenant-a", "tenant-b", "invalid-token")
