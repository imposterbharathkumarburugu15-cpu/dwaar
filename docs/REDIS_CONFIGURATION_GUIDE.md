# Redis Configuration & Coordination Guide

## Overview

Redis serves as the ephemeral distributed coordination layer in PRAMANA (`pramana.distributed.redis_client`). It provides:
1. Fast distributed locking with automatic TTL lease renewal and expiration.
2. Sliding-window rate limiting per institution and per IP address.
3. Metadata caching with prefix-based pattern invalidation.

> **CRITICAL ARCHITECTURAL POLICY:**
> Redis is strictly ephemeral in PRAMANA. It **NEVER** holds primary truth, persistent audit ledgers, or non-recoverable data. If Redis is flushed or restarted, all state can be rebuilt from PostgreSQL or SQLite.

## Configuration Parameters

- Environment Variable: `PRAMANA_REDIS_URL` (Default: `redis://localhost:6379/0`)
- Socket Timeout: 1.5 seconds.
- Connect Timeout: 1.5 seconds.
- Retry on Timeout: True.

## Lock Mechanism

```python
from pramana.distributed.redis_client import default_coordinator

# Context-managed distributed lock with 30-second lease
with default_coordinator.lock("scrutiny:APP-2026-000101", lease_seconds=30) as acquired:
    if not acquired:
        raise HTTPException(409, "Scrutiny already running on another node")
    # Perform scrutiny
```

## Sliding Window Rate Limiting

The rate limiter executes an atomic pipeline incrementing the window key and extending expiration:
```python
allowed, current, remaining = default_coordinator.check_rate_limit(
    identifier=f"user:{user.id}",
    limit=100,
    window_seconds=60,
)
```
When requests exceed the limit, the API immediately returns `HTTP 429 Too Many Requests`.

