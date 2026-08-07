"""Health check endpoint tests."""
import pytest


@pytest.mark.asyncio
async def test_liveness_check(client):
    """Test liveness probe returns 200."""
    response = await client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "UP"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_readiness_check(client):
    """Test readiness probe returns 200."""
    response = await client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["UP", "DEGRADED"]
    assert "checks" in data
    assert "database" in data["checks"]
    assert "redis" in data["checks"]
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_startup_check(client):
    """Test startup probe returns 200."""
    response = await client.get("/health/startup")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "UP"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_endpoints_no_auth(client):
    """Test health endpoints don't require authentication."""
    for endpoint in ["/health/live", "/health/ready", "/health/startup"]:
        response = await client.get(endpoint)
        assert response.status_code == 200
