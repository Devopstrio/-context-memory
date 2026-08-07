# SECURITY.md — Enterprise Security & Compliance Policy

## 1. Security Architecture Summary

The **Context Memory System** incorporates defense-in-depth principles across data, network, compute, and identity layers:

- **Authentication**: JWT token validation enforcing signature integrity, issuer verification (`iss`), audience verification (`aud`), and expiration window (`exp`).
- **Cryptographic Tenant Isolation**: Strict isolation boundaries ensuring multi-tenant data cannot be accessed across tenant boundaries without HMAC authorization tags.
- **RBAC & ABAC Engine**: Granular permission checks paired with attribute-based access controls for data residency and data classification compliance.
- **Data Encryption**: Support for encrypted persistence using AES-256 for memory payloads.
- **Network & Container Hardening**: Non-root container execution (`user: 1000`), read-only root filesystems, dropped Linux capabilities (`ALL`), and explicit Kubernetes NetworkPolicies.

---

## 2. Vulnerability Disclosure & Reporting Protocol

If you discover a potential security vulnerability within this repository:

1. **Do NOT** open a public issue or discussion thread.
2. Email full technical details and reproduction steps to **`engineering@devopstrio.co.uk`**.
3. The security team will acknowledge receipt within 24 hours and provide an estimated patch timeline within 72 hours.

---

## 3. Dependency Scanning & Compliance Checks

Automated static analysis tools executed in CI/CD pipeline runs:
- **Bandit**: Python AST security analysis (`bandit -r src/`)
- **Ruff**: Static code analysis and linting
- **Mypy**: Strict type-safety compliance
