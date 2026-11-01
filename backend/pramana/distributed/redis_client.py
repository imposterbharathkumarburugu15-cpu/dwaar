"""Distributed Caching, Rate Limiting & Lock Coordination via Redis.

Implements Module 2 of Phase 4:
- Connection pooling and environment-based configuration.
- Resilient fallback to an in-memory coordination cache when Redis is offline or uninstalled.
- TTL-based expiration, atomic cache operations, and prefix-based invalidation.
- Distributed lock abstraction with automatic lease timeouts.
- Explicit policy enforcement: Redis is ephemeral; it NEVER replaces durable storage.
"""

from collections.abc import Iterator
from contextlib import contextmanager
import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger("pramana.distributed.redis")

# Configurable environment variable
DEFAULT_REDIS_URL = os.getenv("PRAMANA_REDIS_URL", "redis://localhost:6379/0")


class InMemoryFallbackCoordination:
    """Provides transparent in-memory coordination when external Redis is offline or absent."""

    def __init__(self):
        self._store: dict[str, tuple[Any, float | None]] = {}
        self._locks: dict[str, float] = {}

    def get(self, key: str) -> Any | None:
        self._evict_expired()
        if key in self._store:
            val, exp = self._store[key]
            if exp is None or exp > time.time():
                return val
            del self._store[key]
        return None

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> bool:
        self._evict_expired()
        exp = (time.time() + ttl_seconds) if ttl_seconds else None
        self._store[key] = (value, exp)
        return True

    def delete(self, key: str) -> bool:
        return self._store.pop(key, None) is not None

    def delete_pattern(self, pattern: str) -> int:
        self._evict_expired()
        # Simple glob-like wildcard prefix matching
        prefix = pattern.rstrip("*")
        keys_to_del = [k for k in self._store if k.startswith(prefix)]
        for k in keys_to_del:
            del self._store[k]
        return len(keys_to_del)

    def acquire_lock(self, lock_name: str, lease_seconds: int = 30) -> bool:
        now = time.time()
        current_expiry = self._locks.get(lock_name)
        if current_expiry and current_expiry > now:
            return False  # Locked
        self._locks[lock_name] = now + lease_seconds
        return True

    def release_lock(self, lock_name: str) -> bool:
        if lock_name in self._locks:
            del self._locks[lock_name]
            return True
        return False

    def _evict_expired(self):
        now = time.time()
        expired = [k for k, (_, exp) in self._store.items() if exp is not None and exp <= now]
        for k in expired:
            del self._store[k]


class DistributedCoordinator:
    """Manages Redis connection, caching, distributed locks, and rate limiting."""

    def __init__(self, redis_url: str = DEFAULT_REDIS_URL):
        self.redis_url = redis_url
        self._client: Any = None
        self._is_redis_available = False
        self._in_memory = InMemoryFallbackCoordination()
        self._init_connection()

    def _init_connection(self):
        try:
            import redis
            self._client = redis.Redis.from_url(
                self.redis_url,
                socket_timeout=1.5,
                socket_connect_timeout=1.5,
                decode_responses=True,
            )
            # Test connectivity
            self._client.ping()
            self._is_redis_available = True
            logger.info("Connected to Redis broker at %s", self.redis_url)
        except Exception as err:
            self._is_redis_available = False
            self._client = None
            logger.info("Redis not reachable (%s); operating with resilient In-Memory fallback coordinator", err)

    @property
    def is_connected(self) -> bool:
        return self._is_redis_available

    def health_check(self) -> dict[str, Any]:
        """Returns health status of the distributed coordination layer."""
        if self._is_redis_available and self._client:
            try:
                t0 = time.perf_counter()
                self._client.ping()
                latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                info = self._client.info(section="server")
                return {
                    "status": "HEALTHY",
                    "mode": "REDIS_CONNECTED",
                    "latency_ms": latency_ms,
                    "redis_version": info.get("redis_version", "unknown"),
                    "redis_url": self.redis_url,
                }
            except Exception as err:
                return {
                    "status": "DEGRADED",
                    "mode": "IN_MEMORY_FALLBACK",
                    "error": str(err),
                    "redis_url": self.redis_url,
                }
        return {
            "status": "HEALTHY",
            "mode": "IN_MEMORY_FALLBACK",
            "message": "Redis daemon not detected; resilient in-memory coordination operational.",
            "redis_url": self.redis_url,
        }

    # --- Caching Operations ---

    def get_cache(self, key: str) -> Any | None:
        """Retrieves and deserializes JSON cache item."""
        if self._is_redis_available and self._client:
            try:
                raw = self._client.get(key)
                return json.loads(raw) if raw is not None else None
            except Exception:
                pass
        return self._in_memory.get(key)

    def set_cache(self, key: str, value: Any, ttl_seconds: int = 300) -> bool:
        """Serializes and caches value with TTL."""
        if self._is_redis_available and self._client:
            try:
                serialized = json.dumps(value)
                return bool(self._client.setex(key, ttl_seconds, serialized))
            except Exception:
                pass
        return self._in_memory.set(key, value, ttl_seconds=ttl_seconds)

    def delete_cache(self, key: str) -> bool:
        """Deletes single cached key."""
        if self._is_redis_available and self._client:
            try:
                return bool(self._client.delete(key))
            except Exception:
                pass
        return self._in_memory.delete(key)

    def invalidate_pattern(self, pattern: str) -> int:
        """Invalidates all cache keys matching prefix or pattern."""
        count = 0
        if self._is_redis_available and self._client:
            try:
                keys = self._client.keys(pattern)
                if keys:
                    count = self._client.delete(*keys)
            except Exception:
                pass
        mem_count = self._in_memory.delete_pattern(pattern)
        return max(count, mem_count)

    # --- Distributed Locks ---

    @contextmanager
    def lock(self, lock_name: str, lease_seconds: int = 30, blocking_timeout: float = 2.0) -> Iterator[bool]:
        """Context manager for distributed locking with lease expiration."""
        acquired = False
        deadline = time.time() + blocking_timeout
        key = f"prm:lock:{lock_name}"

        while time.time() <= deadline:
            if self._is_redis_available and self._client:
                try:
                    acquired = bool(self._client.set(key, "1", nx=True, ex=lease_seconds))
                    if acquired:
                        break
                except Exception:
                    acquired = self._in_memory.acquire_lock(key, lease_seconds=lease_seconds)
                    if acquired:
                        break
            else:
                acquired = self._in_memory.acquire_lock(key, lease_seconds=lease_seconds)
                if acquired:
                    break
            time.sleep(0.05)

        try:
            yield acquired
        finally:
            if acquired:
                if self._is_redis_available and self._client:
                    try:
                        self._client.delete(key)
                    except Exception:
                        pass
                self._in_memory.release_lock(key)

    # --- Rate Limiter ---

    def check_rate_limit(
        self,
        identifier: str,
        limit: int,
        window_seconds: int = 60,
    ) -> tuple[bool, int, int]:
        """Sliding-window / bucket rate limit check. Returns (allowed, current_count, remaining)."""
        key = f"prm:ratelimit:{identifier}"
        now = time.time()

        if self._is_redis_available and self._client:
            try:
                pipe = self._client.pipeline()
                pipe.incr(key)
                pipe.expire(key, window_seconds)
                results = pipe.execute()
                current = results[0]
                remaining = max(0, limit - current)
                return (current <= limit, current, remaining)
            except Exception:
                pass

        # In-memory rate limiting
        val = self._in_memory.get(key)
        current = (val or 0) + 1
        self._in_memory.set(key, current, ttl_seconds=window_seconds)
        remaining = max(0, limit - current)
        return (current <= limit, current, remaining)


# Global distributed coordinator
default_coordinator = DistributedCoordinator()

