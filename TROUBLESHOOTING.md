# TROUBLESHOOTING.md — Common Failure Modes & Debugging Guide

## Diagnostic Matrix

| Error Code | Observed Behavior | Root Cause | Resolution |
| :--- | :--- | :--- | :--- |
| `AUTH_001` | HTTP 401 `Invalid authorization header format` | Missing `Bearer ` prefix in HTTP header. | Format header as `Authorization: Bearer <TOKEN>`. |
| `AUTH_002` | HTTP 401 `Access token has expired` | JWT token passed validation window (`exp`). | Obtain refreshed token using refresh flow. |
| `TENANT_001` | HTTP 403 `Tenant boundary violation` | `X-Tenant-ID` header does not match JWT `tenant_id` claim. | Ensure HTTP header matches authenticated JWT claim. |
| `RATE_001` | HTTP 429 `Rate limit exceeded` | Tenant exceeded `RATE_LIMIT_REQUESTS_PER_MINUTE`. | Implement backoff logic or increase tenant rate limit quota in DB. |
| `INT_002` | HTTP 500 `DATABASE_ERROR` | Connection pool exhausted or database query timeout. | Check PostgreSQL stats and pool sizing settings. |

---

## Interactive Debugging Commands

### 1. Tail Live Structured Application Logs
Filter JSON logs by level or correlation ID using `jq`:

```bash
kubectl logs -f deployment/context-memory -n context-memory \
  | jq -r 'select(.level=="ERROR") | {timestamp, message, correlation_id, error}'
```

### 2. Verify Database Connection & Migration Status
```bash
# Verify Alembic current schema version
kubectl exec -it deploy/context-memory -n context-memory -- alembic current
```

### 3. Check Redis Connection & Key Eviction
```bash
kubectl exec -it deploy/context-memory -n context-memory -- redis-cli -u "redis://redis-service:6379" info stats
```
