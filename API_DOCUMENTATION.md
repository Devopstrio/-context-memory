# API_DOCUMENTATION.md — REST API Technical Specification

## Base URL
```text
http://<host>:8000/v1
```

## Authentication & Headers
All requests to protected endpoints require the following headers:
- `Authorization: Bearer <JWT_ACCESS_TOKEN>`
- `X-Tenant-ID: <TENANT_IDENTIFIER>`
- `X-Correlation-ID`: (Optional) UUID for request tracing.

---

## 1. Health & Diagnostics Endpoints

### 1.1 Liveness Probe
- **HTTP Method**: `GET`
- **Path**: `/health/live`
- **Auth Required**: No
- **Response 200 OK**:
  ```json
  {
    "status": "UP",
    "timestamp": "2026-08-06T21:00:00Z"
  }
  ```

### 1.2 Readiness Probe
- **HTTP Method**: `GET`
- **Path**: `/health/ready`
- **Auth Required**: No
- **Response 200 OK**:
  ```json
  {
    "status": "UP",
    "checks": {
      "database": "UP",
      "redis": "UP"
    },
    "timestamp": "2026-08-06T21:00:00Z"
  }
  ```

---

## 2. Memory Management Endpoints

### 2.1 Create Memory
- **HTTP Method**: `POST`
- **Path**: `/v1/memories`
- **Request Body**:
  ```json
  {
    "tenant_id": "tenant-corp-alpha",
    "session_id": "sess-9901",
    "user_id": "usr-4412",
    "content": "User prefers dark mode and Python programming language.",
    "metadata": {
      "source": "onboarding_chat"
    },
    "importance": 8.5,
    "memory_type": "factual"
  }
  ```
- **Response 201 Created**:
  ```json
  {
    "id": "c39a812b-31a4-4a27-a021-3e42111d4d12",
    "tenant_id": "tenant-corp-alpha",
    "session_id": "sess-9901",
    "user_id": "usr-4412",
    "content": "User prefers dark mode and Python programming language.",
    "metadata": {
      "source": "onboarding_chat"
    },
    "importance": 8.5,
    "memory_type": "factual",
    "created_at": "2026-08-06T21:00:00Z",
    "updated_at": "2026-08-06T21:00:00Z",
    "expires_at": "2026-11-04T21:00:00Z"
  }
  ```

### 2.2 Get Memory by ID
- **HTTP Method**: `GET`
- **Path**: `/v1/memories/{memory_id}`
- **Response 200 OK**:
  ```json
  {
    "id": "c39a812b-31a4-4a27-a021-3e42111d4d12",
    "tenant_id": "tenant-corp-alpha",
    "session_id": "sess-9901",
    "user_id": "usr-4412",
    "content": "User prefers dark mode and Python programming language.",
    "metadata": { "source": "onboarding_chat" },
    "importance": 8.5,
    "memory_type": "factual",
    "created_at": "2026-08-06T21:00:00Z",
    "updated_at": "2026-08-06T21:00:00Z",
    "expires_at": "2026-11-04T21:00:00Z"
  }
  ```

### 2.3 List Session Memories
- **HTTP Method**: `GET`
- **Path**: `/v1/memories`
- **Query Parameters**:
  - `session_id` (string, required): Session ID.
  - `page` (integer, default: 1): Page number.
  - `size` (integer, default: 20): Items per page.
  - `memory_type` (string, optional): Filter by memory type.
- **Response 200 OK**:
  ```json
  {
    "items": [],
    "total": 45,
    "page": 1,
    "size": 20,
    "pages": 3
  }
  ```

### 2.4 Semantic Memory Search
- **HTTP Method**: `POST`
- **Path**: `/v1/memories/search`
- **Request Body**:
  ```json
  {
    "tenant_id": "tenant-corp-alpha",
    "query": "What are the user's interface preferences?",
    "top_k": 5,
    "memory_type": "factual"
  }
  ```
- **Response 200 OK**:
  ```json
  {
    "results": [
      {
        "id": "c39a812b-31a4-4a27-a021-3e42111d4d12",
        "content": "User prefers dark mode and Python programming language.",
        "similarity_score": 0.8912,
        "metadata": { "source": "onboarding_chat" },
        "memory_type": "factual",
        "created_at": "2026-08-06T21:00:00Z"
      }
    ],
    "query": "What are the user's interface preferences?",
    "total": 1
  }
  ```

---

## 3. Session & Context Hydration Endpoints

### 3.1 Hydrate Session Context
- **HTTP Method**: `POST`
- **Path**: `/v1/sessions/hydrate`
- **Request Body**:
  ```json
  {
    "tenant_id": "tenant-corp-alpha",
    "session_id": "sess-9901",
    "user_id": "usr-4412",
    "max_tokens": 4000
  }
  ```
- **Response 200 OK**:
  ```json
  {
    "session_id": "sess-9901",
    "context": "User prefers dark mode and Python programming language.",
    "token_count": 12,
    "memory_count": 1
  }
  ```

---

## 4. Standardized Error Response Schema

In the event of an error, all endpoints return a consistent JSON payload:
```json
{
  "error_code": "AUTH_001",
  "message": "Invalid authorization header format",
  "details": null,
  "correlation_id": "req-8812-abc",
  "timestamp": "2026-08-06T21:00:00Z"
}
```
