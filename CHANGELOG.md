# CHANGELOG.md — Release History

All notable changes to the `context-memory` project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2024-01-01

### Added
- **Core Architecture**: Enterprise-grade multi-tenant Context Memory service built on FastAPI and Python 3.11.
- **Persistence Layer**: Async SQLAlchemy 2.0 ORM models for `tenants`, `sessions`, `memories`, `memory_embeddings`, and `audit_logs` with PostgreSQL `asyncpg` driver.
- **Database Migrations**: Alembic async migration environment and initial schema setup revision (`001_initial_schema.py`).
- **Cache & Resilience**: Async Redis client featuring an automated 3-state Circuit Breaker (`CLOSED`, `OPEN`, `HALF_OPEN`) and in-memory fallback store.
- **Security & Authorization**: JWT token validation engine, cryptographic tenant boundary isolation (`TenantIsolationGuard`), and dual RBAC/ABAC access control engine.
- **Semantic Retrieval**: Modular vector embedding framework featuring OpenAI and deterministic test embedders.
- **Session Context Hydration**: Token budget management and memory context hydration service (`SessionHydrator`).
- **Telemetry**: Prometheus metrics instrumentation (`/metrics`) and OpenTelemetry OTLP gRPC distributed tracing integration.
- **Deployment Manifests**: Multi-stage production `Dockerfile`, `docker-compose.yml`, Kustomize base/overlays (`dev`, `staging`, `prod`), and Helm v3 chart.
- **CI/CD**: Complete GitHub Actions workflow suite for linting, testing, image building, container testing, and Helm packaging.
