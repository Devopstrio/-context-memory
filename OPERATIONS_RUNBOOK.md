# OPERATIONS_RUNBOOK.md — Context Memory Operational Runbook

## 1. System Overview & SLOs

- **Service Name**: Context Memory System (`context-memory`)
- **Target Availability**: 99.95% uptime
- **Latency SLOs**:
  - Memory Read / Search: p95 < 50ms, p99 < 150ms
  - Memory Creation: p95 < 100ms
  - Session Hydration: p95 < 80ms

---

## 2. Emergency Escalation & On-Call Protocols

1. **Severity 1 (Service Outage / PagerDuty Alert)**:
   - Primary: On-Call Site Reliability Engineer
   - Secondary: Lead DevOps Engineer
2. **Severity 2 (Performance Degradation / Circuit Breaker Open)**:
   - Primary: Secondary On-Call SRE / DevOps Team

---

## 3. Incident Management Runbooks

### Runbook A: High Database Connection Usage or Timeout Errors
**Symptoms**: Prometheus alert `DatabaseConnectionPoolExhausted` triggers, HTTP 500 responses with `DATABASE_ERROR`.

**Diagnostic Steps**:
1. Inspect active database connections in Grafana or via psql:
   ```sql
   SELECT count(*), state, application_name FROM pg_stat_activity GROUP BY state, application_name;
   ```
2. Verify application horizontal pod counts.

**Remediation**:
- Temporarily increase `DATABASE_POOL_SIZE` or connection limits on PostgreSQL.
- Scale up pod replicas if connection exhaustion is due to high CPU thread lock:
  ```bash
  kubectl scale deployment context-memory --replicas=10 -n context-memory
  ```

---

### Runbook B: Redis Circuit Breaker Tripped (OPEN State)
**Symptoms**: Metric `context_memory_circuit_breaker_state{service="redis"} == 1`. Logs indicate `RedisUnavailableError`.

**Diagnostic Steps**:
1. Ping Redis cluster directly from a debug pod:
   ```bash
   kubectl exec -it deploy/context-memory -n context-memory -- redis-cli -u "redis://redis-service:6379" ping
   ```
2. Check Redis memory utilization (`INFO memory`).

**Remediation**:
- System automatically routes traffic to in-memory fallback stores while circuit breaker is `OPEN`.
- If Redis is OOM, flush evicted keys or adjust maxmemory eviction policies:
  ```bash
  redis-cli -h redis-service config set maxmemory-policy allkeys-lru
  ```

---

### Runbook C: High Memory Generation Latency / Embedding Outages
**Symptoms**: High `context_memory_embedding_duration_seconds`.

**Diagnostic Steps**:
1. Verify external embedding provider (OpenAI API status) or fallback embedder state.
2. Inspect log errors filtered by `event="OpenAI rate limit hit"`.

**Remediation**:
- Fallback embedders handle temporary rate limits automatically via exponential backoff retries.

---

## 4. Database Maintenance & Schema Migrations

Always run schema migrations prior to initiating zero-downtime rolling upgrades:
```bash
# Execute Alembic migration from administrative pod
kubectl exec -it deploy/context-memory -n context-memory -- alembic upgrade head
```
