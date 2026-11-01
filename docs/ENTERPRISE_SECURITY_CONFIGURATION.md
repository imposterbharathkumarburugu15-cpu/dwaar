# Enterprise Security Configuration

## Production Security Checklist
- [x] TLS 1.3 enforced at Ingress boundary with HSTS `max-age=31536000`.
- [x] Cookie security: `__Host-` prefix with `HttpOnly`, `SameSite=Strict`, `Secure=True`.
- [x] Database encryption: TLS connection strings, AES-256 encrypted tablespaces.
- [x] Object storage: Server-side SSE-S3 or SSE-KMS encryption.
- [x] Secret injection: Managed via Kubernetes Secrets / HashiCorp Vault; no plaintext secrets in code or git.
- [x] Audit ledger: Hash-chained Merkle structure signed with Ed25519 officer keys.

