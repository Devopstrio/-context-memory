# ARCHITECTURE.md — Context Memory Architecture & System Design

## 1. Executive Summary

The **Context Memory System** is designed to solve the long-term context retention and retrieval bottleneck in LLM applications. Standard LLM context windows are limited, expensive, and stateless. This system acts as an external state management and semantic indexing layer, providing multi-tenant applications with high-concurrency, low-latency, and compliant memory hydration.

---

## 2. High-Level Architecture Diagram

```text
                       ┌───────────────────────────────────────┐
                       │           Client Application          │
                       └──────────────────┬────────────────────┘
                                          │ HTTP / REST (JWT + X-Tenant-ID)
                                          ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                FastAPI Gateway Layer                                   │
│  ┌─────────────────────────┐  ┌──────────────────────────┐  ┌───────────────────────┐  │
│  │ Correlation ID / Logging │  │ Security Headers / Rate  │  │ Tenant Context Guard  │  │
│  └─────────────────────────┘  └──────────────────────────┘  └───────────────────────┘  │
└─────────────────────────────────────────┬──────────────────────────────────────────────┘
                                          │
                                          ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                Security & Governance                                   │
│  ┌─────────────────────────┐  ┌──────────────────────────┐  ┌───────────────────────┐  │
│  │ JWT Authenticator       │  │ RBAC / ABAC Engine       │  │ Retention & Audit     │  │
│  └─────────────────────────┘  └──────────────────────────┘  └───────────────────────┘  │
└─────────────────────────────────────────┬──────────────────────────────────────────────┘
                                          │
                                          ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                    Domain Services                                     │
│  ┌─────────────────────────────────────┐      ┌─────────────────────────────────────┐  │
│  │           Memory Service            │      │           Session Service           │  │
│  │ - Add / Get / Search / Soft-Delete  │      │ - Upsert / Active / Complete / Hydr │  │
│  └──────────────────┬──────────────────┘      └──────────────────┬──────────────────┘  │
└─────────────────────┼────────────────────────────────────────────┼─────────────────────┘
                      │                                            │
                      ▼                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                  Persistence Layer                                     │
│  ┌─────────────────────────────────────┐      ┌─────────────────────────────────────┐  │
│  │           Redis Cache               │      │        PostgreSQL Database          │  │
│  │ - Session context caching           │      │ - Memories & Memory Embeddings      │  │
│  │ - Circuit Breaker fallback          │      │ - Sessions, Audit Logs, Tenants     │  │
│  └─────────────────────────────────────┘      └─────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Core Architectural Components

### 3.1 API Gateway & Middleware Pipeline
All incoming HTTP requests pass through an ASGI middleware chain prior to router execution:
- **CorrelationIdMiddleware**: Generates or propagates `X-Correlation-ID` and `X-Request-ID` headers across request contexts.
- **RequestLoggingMiddleware**: Emits structured JSON logs containing request metadata, response status, and processing duration metrics.
- **TenantContextMiddleware**: Extracts `X-Tenant-ID` header and binds tenant context to `structlog` async context variables.
- **RateLimitMiddleware**: Enforces sliding-window rate limits per tenant using Redis key counters with local in-memory fallback.
- **SecurityHeadersMiddleware**: Injects enterprise security response headers (`X-Frame-Options`, `HSTS`, `Content-Security-Policy`, etc.).

### 3.2 Security & Multi-Tenancy Architecture
- **Cryptographic Tenant Isolation**: The `TenantIsolationGuard` verifies that the `X-Tenant-ID` HTTP header strictly matches the authenticated `tenant_id` claim present inside the validated JWT. HMAC-SHA256 signatures validate cross-tenant operations.
- **RBAC & ABAC Engine**: Combines Role-Based Access Control (`reader`, `writer`, `admin`, `super_admin`) with Attribute-Based Access Control enforcing rules around data classification (e.g., `RESTRICTED_PHI`) and geographical data residency.

### 3.3 Domain Services & Data Access Pattern
- **Repository Pattern**: Abstracted database access using SQLAlchemy 2.0 `AsyncSession`. Direct SQL execution is prohibited inside service modules.
- **Session Hydration**: `SessionHydrator` fetches historical session memories, ranks them by importance and semantic similarity, and packages context within configured token constraints (`max_tokens`).

### 3.4 Resilience & Caching Architecture
- **Redis Client with Circuit Breaker**: Wraps Redis operations inside a 3-state circuit breaker (`CLOSED`, `OPEN`, `HALF_OPEN`). When Redis fails or encounters network timeouts, operations automatically degrade gracefully to an in-memory fallback store.

---

## 4. Data Storage & Schema Design

### 4.1 Database Models
- **tenants**: Tenant settings, tier, limits, retention days, and encryption flags.
- **sessions**: Tracks session state (`active`, `paused`, `completed`, `expired`), token usage, and snapshot metadata.
- **memories**: Stores text content, content hash (SHA-256 for deduplication), importance rating (0.0 - 10.0), memory type, and expiry timestamp.
- **memory_embeddings**: Holds high-dimensional embedding vectors stored as JSONB with model metadata and checksum validation.
- **audit_logs**: Immutable audit records for compliance tracking.

---

## 5. Telemetry & Observability Framework

- **Prometheus Metrics**: Exposes HTTP request latency, active database connection counts, cache hits/misses, embedding generation duration, and circuit breaker states at `/metrics`.
- **Distributed Tracing**: OpenTelemetry gRPC instrumentation automatically traces HTTP entrypoints, Redis cache lookups, and SQLAlchemy database queries via OTLP exporters.
