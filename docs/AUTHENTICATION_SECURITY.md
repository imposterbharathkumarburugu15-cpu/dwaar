# Authentication & Session Security Architecture

## Authentication Pipeline
1. **Password Hashing**: Argon2id via `PasswordHasher` with salt and memory-hard parameters.
2. **Session Storage**: Server-side session tokens stored as SHA-256 digests in SQLite / PostgreSQL `auth_sessions` table.
3. **Cookie Attributes**:
   - `Name`: `__Host-pramana_session` over HTTPS (`pramana_session` local fallback).
   - `HttpOnly`: True (inaccessible to JavaScript, defeating XSS exfiltration).
   - `SameSite`: Strict.
   - `Secure`: True when HTTPS is enabled.
   - `Path`: `/`.
4. **Lockout Controls**:
   - IP-level sliding window limit.
   - Username-level failure counter.
   - Automatic `429 Too Many Requests` with `Retry-After` header.

