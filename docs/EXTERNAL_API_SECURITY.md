# External API Security Architecture

## Perimeter Security Controls
- **SSRF Prevention**: Strict domain allowlist (`apisetu.gov.in`, `digilocker.gov.in`, `aicte-india.org`, `nic.in`). Rejection of all private, link-local, and loopback IP ranges.
- **Circuit Breaker**: Prevents cascading failures during external downtime. Trips to OPEN state after 5 consecutive failures; transitions to HALF_OPEN after 30s.
- **Payload Limits**: 25 MB maximum response size cap to prevent memory exhaustion attacks.
- **Credential Redaction**: Authorization headers and client secrets are stripped from request and response logging.

