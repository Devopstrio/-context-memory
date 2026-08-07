# DEPLOYMENT_GUIDE.md — Enterprise Production Deployment Guide

## 1. Overview & Architecture Requirements

This guide outlines deployment procedures for running `context-memory` in production environments.

### System Requirements
- **Compute**: Minimum 3 Replicas (2 vCPU, 2GB RAM per pod)
- **Database**: PostgreSQL 16+ with SSL connections enabled
- **Cache**: Redis 7+ cluster or sentinel with persistence enabled
- **Ingress**: TLS 1.3 termination at edge ingress controller

---

## 2. Configuration & Environment Variables

All settings are configured via environment variables injected into the runtime container:

| Variable Name | Required | Default Value | Description |
| :--- | :---: | :--- | :--- |
| `ENVIRONMENT` | Yes | `production` | Active deployment stage (`production`, `staging`, `development`). |
| `DATABASE_URL` | Yes | - | Async PostgreSQL connection URI (`postgresql+asyncpg://...`). |
| `DATABASE_POOL_SIZE` | No | `20` | Database connection pool size. |
| `REDIS_URL` | Yes | - | Redis connection URI (`redis://...` or `rediss://...`). |
| `JWT_SECRET_KEY` | Yes | - | Secret key used for JWT signature verification (min 32 bytes). |
| `JWT_ISSUER` | Yes | `https://auth.enterprise.internal` | Valid JWT token issuer claim. |
| `JWT_AUDIENCE` | Yes | `context-memory-api` | Valid JWT token audience claim. |
| `ENCRYPTION_KEY` | Yes | - | AES-256 data encryption key. |
| `OTLP_EXPORTER_ENDPOINT`| No | `None` | OpenTelemetry gRPC collector endpoint URL. |

---

## 3. Docker Container Image Build

To build the production-ready multi-stage container image locally or in CI/CD:

```bash
docker build \
  --target runtime \
  -t ghcr.io/devopstrio/context-memory:v1.0.0 .
```

---

## 4. Kubernetes Deployment via Kustomize

Navigate to the deployment overlay directory:
```bash
cd deployment/kubernetes/overlays/prod
```

Update secrets in your secret manager or create the Kubernetes secret object:
```bash
kubectl create secret generic context-memory-secrets \
  --namespace context-memory \
  --from-literal=DATABASE_URL="postgresql+asyncpg://user:pass@postgres:5432/context_memory" \
  --from-literal=REDIS_URL="redis://redis:6379/0" \
  --from-literal=JWT_SECRET_KEY="super-secret-enterprise-jwt-key-32bytes-minimum" \
  --from-literal=ENCRYPTION_KEY="context-memory-encryption-key-32bytes-here"
```

Deploy using Kustomize:
```bash
kubectl apply -k .
```

---

## 5. Kubernetes Deployment via Helm

Deploy the release using the Helm chart:
```bash
helm upgrade --install context-memory ./deployment/helm \
  --namespace context-memory \
  --create-namespace \
  --set replicaCount=5 \
  --set secrets.databaseUrl="postgresql+asyncpg://user:pass@postgres:5432/context_memory" \
  --set secrets.redisUrl="redis://redis:6379/0" \
  --set secrets.jwtSecretKey="super-secret-enterprise-jwt-key-32bytes-minimum" \
  --set secrets.encryptionKey="context-memory-encryption-key-32bytes-here"
```

---

## 6. Verification & Health Validation

Validate pod status and health check endpoints following deployment:
```bash
# Check pod rollout status
kubectl rollout status deployment/context-memory -n context-memory

# Execute readiness probe check
kubectl exec -it deploy/context-memory -n context-memory -- curl http://localhost:8000/health/ready
```
