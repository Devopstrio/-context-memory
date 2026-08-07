<div align="center">

<img src="https://raw.githubusercontent.com/Devopstrio/.github/main/assets/Browser_logo.png" height="90"/>

<h1>context-memory</h1>

<p><strong>Enterprise Context Engineering Platform - High-Performance Context & Model Router</strong></p>

[![Build Status](https://img.shields.io/badge/Build-Passing-10B981?style=flat-square)](https://devopstrio.co.uk)
[![Python Version](https://img.shields.io/badge/Python-3.11%2B-3776AB.svg?style=flat-square)](https://python.org)
[![Context Router](https://img.shields.io/badge/Context-Router-8B5CF6?style=flat-square)](https://devopstrio.co.uk)
[![Terraform](https://img.shields.io/badge/IaC-OpenTofu_1.8.5-FF5733?style=flat-square)](https://opentofu.org)

</div>

---

## Technical Stack & Key Capabilities

- **Framework & Core**: Python 3.11, FastAPI (`uvicorn` + `uvloop` + `httptools`), Pydantic v2
- **Database & Storage**: PostgreSQL 16 (AsyncSQLAlchemy + `asyncpg` + Alembic migrations), Redis 7 (`redis-py` async + `hiredis`)
- **Security & Multi-Tenancy**: PyJWT (HS256/RS256), Cryptographic Tenant Tagging, RBAC/ABAC Policy Engine, AES-GCM Payload Encryption
- **Observability**: OpenTelemetry gRPC OTLP Tracing, Prometheus Client Metrics, `structlog` JSON Logging
- **Containerization & Orchestration**: Multi-stage Docker build (`slim-bookworm`), Kubernetes Base & Overlays (Dev/Staging/Prod), Helm Chart v2

---

## Repository Structure

```text
.
├── .github/                  # CI/CD Workflows (GitHub Actions)
├── alembic/                  # Database migration scripts and async env configuration
│   ├── versions/             # Migration revisions
│   └── env.py                # Alembic async engine setup
├── deployment/               # Enterprise Deployment Manifests
│   ├── helm/                 # Production Helm v3 Chart
│   └── kubernetes/           # Kustomize manifests (base & overlays)
├── src/
│   └── context_memory/       # Primary Source Code
│       ├── api/              # FastAPI routers & request validation schemas
│       ├── cache/            # Redis async client with Circuit Breaker
│       ├── config/           # Pydantic BaseSettings & env management
│       ├── embeddings/       # Embedding generation & OpenAI integrations
│       ├── governance/       # Retention policies & lifecycle hooks
│       ├── models/           # SQLAlchemy 2.0 async ORM models
│       ├── persistence/      # Repository pattern database access layers
│       ├── security/         # JWT authenticator, RBAC/ABAC, Tenant Guard
│       ├── services/         # Memory & Session domain service engines
│       ├── session/          # LLM Context Hydration & Token Budgeting
│       ├── telemetry/        # OpenTelemetry & Prometheus instrumentation
│       └── utils/            # Middleware, custom exceptions, logging setup
├── tests/                    # Unit & Integration test suite
├── Dockerfile                # Production multi-stage Docker build
├── docker-compose.yml        # Local development infrastructure
├── Makefile                  # Developer workflow automation
└── pyproject.toml            # Project packaging & dependency setup
```

---

## Quick Start Guide

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- PostgreSQL 16+ & Redis 7+ (if running natively)

### Local Development Setup

1. **Clone Repository & Environment Setup**:
   ```bash
   git clone https://github.com/Devopstrio/-context-memory.git
   cd context-memory
   python -m venv .venv
   source .venv/bin/activate
   make install-dev
   ```

2. **Start Infrastructure Services**:
   ```bash
   make docker-up
   ```

3. **Apply Database Migrations**:
   ```bash
   make migrate
   ```

4. **Launch Application Server**:
   ```bash
   make run
   ```
   The API server will be available at `http://localhost:8000`. Interactive OpenAPI documentation is accessible at `http://localhost:8000/docs`.

---

## Running Tests & Quality Checks

Execute unit tests, integration tests, static code analysis, and coverage reporting via Makefile:

```bash
# Run all test suites
make test

# Run unit tests only
make test-unit

# Run integration tests only
make test-integration

# Generate HTML coverage report
make test-coverage

# Run linters (ruff, mypy strict, bandit)
make lint
```

---

## Security Policy

Security issues should be reported directly to `engineering@devopstrio.co.uk`. Do not open public issues for security vulnerabilities. See `SECURITY.md` for full compliance and reporting protocols.

---

<div align="center">
© 2026 Devopstrio — Engineering the Autonomous Enterprise.
</div>
