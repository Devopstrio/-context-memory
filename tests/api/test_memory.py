"""Memory API endpoint tests."""

import uuid

import pytest


@pytest.mark.asyncio
async def test_create_memory_unauthorized(client):
    """Test creating memory without authentication."""
    response = await client.post(
        "/v1/memories",
        json={
            "tenant_id": "test-tenant",
            "session_id": "test-session",
            "user_id": "test-user",
            "content": "Test content",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_memory_success(client, auth_headers, test_memory_data):
    """Test successful memory creation."""
    response = await client.post(
        "/v1/memories",
        headers=auth_headers,
        json=test_memory_data,
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["tenant_id"] == test_memory_data["tenant_id"]
    assert data["session_id"] == test_memory_data["session_id"]
    assert data["content"] == test_memory_data["content"]
    assert data["importance"] == test_memory_data["importance"]
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_create_memory_empty_content(client, auth_headers):
    """Test creating memory with empty content fails."""
    response = await client.post(
        "/v1/memories",
        headers=auth_headers,
        json={
            "tenant_id": "tenant-corp-alpha",
            "session_id": "test-session",
            "user_id": "test-user",
            "content": "",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_memory_tenant_mismatch(client, auth_headers):
    """Test creating memory with mismatched tenant fails."""
    response = await client.post(
        "/v1/memories",
        headers=auth_headers,
        json={
            "tenant_id": "tenant-corp-beta",
            "session_id": "test-session",
            "user_id": "test-user",
            "content": "Test content",
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_memory_not_found(client, auth_headers):
    """Test retrieving non-existent memory."""
    random_id = str(uuid.uuid4())
    response = await client.get(
        f"/v1/memories/{random_id}",
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_memory_success(client, auth_headers, test_memory_data):
    """Test retrieving a created memory."""
    create_response = await client.post(
        "/v1/memories",
        headers=auth_headers,
        json=test_memory_data,
    )
    memory_id = create_response.json()["id"]

    response = await client.get(
        f"/v1/memories/{memory_id}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == memory_id
    assert data["content"] == test_memory_data["content"]


@pytest.mark.asyncio
async def test_list_memories_pagination(client, auth_headers, test_memory_data):
    """Test listing memories with pagination."""
    for i in range(5):
        test_memory_data["content"] = f"Test content {i}"
        await client.post(
            "/v1/memories",
            headers=auth_headers,
            json=test_memory_data,
        )

    response = await client.get(
        "/v1/memories",
        headers=auth_headers,
        params={
            "session_id": test_memory_data["session_id"],
            "page": 1,
            "size": 3,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "size" in data
    assert "pages" in data
    assert len(data["items"]) <= 3
    assert data["size"] == 3


@pytest.mark.asyncio
async def test_update_memory_success(client, auth_headers, test_memory_data):
    """Test updating a memory."""
    create_response = await client.post(
        "/v1/memories",
        headers=auth_headers,
        json=test_memory_data,
    )
    memory_id = create_response.json()["id"]

    response = await client.put(
        f"/v1/memories/{memory_id}",
        headers=auth_headers,
        json={
            "content": "Updated test content",
            "importance": 8.0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "Updated test content"
    assert data["importance"] == 8.0


@pytest.mark.asyncio
async def test_delete_memory_success(client, auth_headers, test_memory_data):
    """Test deleting a memory."""
    create_response = await client.post(
        "/v1/memories",
        headers=auth_headers,
        json=test_memory_data,
    )
    memory_id = create_response.json()["id"]

    response = await client.delete(
        f"/v1/memories/{memory_id}",
        headers=auth_headers,
    )
    assert response.status_code == 204

    get_response = await client.get(
        f"/v1/memories/{memory_id}",
        headers=auth_headers,
    )
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_search_memories(client, auth_headers, test_memory_data):
    """Test semantic memory search."""
    await client.post(
        "/v1/memories",
        headers=auth_headers,
        json=test_memory_data,
    )

    response = await client.post(
        "/v1/memories/search",
        headers=auth_headers,
        json={
            "tenant_id": "tenant-corp-alpha",
            "query": "test memory",
            "top_k": 5,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert "query" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_hydrate_session(client, auth_headers):
    """Test session hydration."""
    response = await client.post(
        "/v1/sessions/hydrate",
        headers=auth_headers,
        json={
            "tenant_id": "tenant-corp-alpha",
            "session_id": "test-hydration-session",
            "user_id": "test-user",
            "max_tokens": 2000,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert "context" in data
    assert "token_count" in data
    assert "memory_count" in data


@pytest.mark.asyncio
async def test_expired_token_rejected(client, expired_token):
    """Test expired token is rejected."""
    response = await client.post(
        "/v1/memories",
        headers={
            "Authorization": f"Bearer {expired_token}",
            "X-Tenant-ID": "tenant-corp-alpha",
        },
        json={
            "tenant_id": "tenant-corp-alpha",
            "session_id": "test-session",
            "user_id": "test-user",
            "content": "Test content",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_different_tenant_access_denied(client, different_tenant_token):
    """Test accessing resources of different tenant is denied."""
    response = await client.post(
        "/v1/memories",
        headers={
            "Authorization": f"Bearer {different_tenant_token}",
            "X-Tenant-ID": "tenant-corp-alpha",
        },
        json={
            "tenant_id": "tenant-corp-alpha",
            "session_id": "test-session",
            "user_id": "test-user",
            "content": "Test content",
        },
    )
    assert response.status_code == 403
