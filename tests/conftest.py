"""Pytest fixtures and configuration for Context Memory tests."""
import asyncio
import os
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from context_memory.config.settings import get_settings
from context_memory.main import app
from context_memory.models.base import Base
from context_memory.security.jwt_auth import JWTAuthenticator

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:postgres@localhost:5432/context_memory_test"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"
os.environ["LOG_LEVEL"] = "ERROR"


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def settings():
    """Return test settings."""
    return get_settings()


@pytest.fixture(scope="session")
def authenticator() -> JWTAuthenticator:
    """Return JWTAuthenticator instance."""
    return JWTAuthenticator()


@pytest.fixture
def valid_token(authenticator: JWTAuthenticator) -> str:
    """Generate a valid test JWT token."""
    return authenticator.generate_test_token(
        tenant_id="tenant-corp-alpha",
        roles=["context:read", "memory:write", "session:read"],
    )


@pytest.fixture
def admin_token(authenticator: JWTAuthenticator) -> str:
    """Generate an admin test JWT token."""
    return authenticator.generate_test_token(
        tenant_id="tenant-corp-alpha",
        roles=["admin", "memory:admin", "session:admin"],
    )


@pytest.fixture
def reader_token(authenticator: JWTAuthenticator) -> str:
    """Generate a reader test JWT token."""
    return authenticator.generate_test_token(
        tenant_id="tenant-corp-alpha",
        roles=["reader", "context:read"],
    )


@pytest.fixture
def expired_token(authenticator: JWTAuthenticator) -> str:
    """Generate an expired test JWT token."""
    return authenticator.generate_test_token(
        tenant_id="tenant-corp-alpha",
        expires_in_seconds=-3600,
    )


@pytest.fixture
def different_tenant_token(authenticator: JWTAuthenticator) -> str:
    """Generate a token for a different tenant."""
    return authenticator.generate_test_token(
        tenant_id="tenant-corp-beta",
        roles=["context:read"],
    )


@pytest_asyncio.fixture
async def test_engine():
    """Create test database engine."""
    test_engine = create_async_engine(
        "postgresql+asyncpg://postgres:postgres@localhost:5432/context_memory_test",
        echo=False,
    )
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield test_engine
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create test database session."""
    async_session = async_sessionmaker(test_engine, expire_on_commit=False)
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP test client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def test_memory_data() -> dict:
    """Return sample memory data for testing."""
    return {
        "tenant_id": "tenant-corp-alpha",
        "session_id": "test-session-001",
        "user_id": "test-user-001",
        "content": "This is a test memory for integration testing",
        "metadata": {"source": "test", "priority": "high"},
        "importance": 5.0,
        "memory_type": "general",
    }


@pytest.fixture
def auth_headers(valid_token: str) -> dict:
    """Return authorization headers with valid token."""
    return {
        "Authorization": f"Bearer {valid_token}",
        "X-Tenant-ID": "tenant-corp-alpha",
        "X-Correlation-ID": "test-correlation-id",
    }


@pytest.fixture
def admin_auth_headers(admin_token: str) -> dict:
    """Return authorization headers with admin token."""
    return {
        "Authorization": f"Bearer {admin_token}",
        "X-Tenant-ID": "tenant-corp-alpha",
    }
