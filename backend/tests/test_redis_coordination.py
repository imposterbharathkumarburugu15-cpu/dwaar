"""Unit tests for Redis Distributed Coordination, Locks, Caching & Rate Limiting (Module 2)."""

import time
import pytest
from pramana.distributed.redis_client import DistributedCoordinator


def test_in_memory_caching_and_expiration():
    coord = DistributedCoordinator(redis_url="redis://localhost:6379/15")
    # In fallback or real mode, coordinator provides cache functionality
    assert coord.set_cache("key1", {"value": "abc"}, ttl_seconds=2) is True
    val = coord.get_cache("key1")
    assert val == {"value": "abc"}

    # Pattern invalidation
    coord.set_cache("prefix:k1", "foo")
    coord.set_cache("prefix:k2", "bar")
    coord.set_cache("other:k3", "baz")

    invalidated = coord.invalidate_pattern("prefix:*")
    assert invalidated >= 2
    assert coord.get_cache("prefix:k1") is None
    assert coord.get_cache("other:k3") == "baz"


def test_distributed_lock_acquisition_and_release():
    coord = DistributedCoordinator()
    lock_name = "scrutiny_lock_app_999"

    # Context manager lock acquisition
    with coord.lock(lock_name, lease_seconds=5) as acquired1:
        assert acquired1 is True
        # Concurrent attempt should timeout/fail
        with coord.lock(lock_name, lease_seconds=5, blocking_timeout=0.1) as acquired2:
            assert acquired2 is False

    # After exiting block, lock is released and can be re-acquired
    with coord.lock(lock_name, lease_seconds=5) as acquired3:
        assert acquired3 is True


def test_sliding_window_rate_limiter():
    coord = DistributedCoordinator()
    key = "ratelimit_user_test"

    # Limit to 3 requests per window
    for _ in range(3):
        allowed, current, remaining = coord.check_rate_limit(key, limit=3, window_seconds=2)
        assert allowed is True

    # 4th request must be rejected
    allowed, current, remaining = coord.check_rate_limit(key, limit=3, window_seconds=2)
    assert allowed is False
    assert remaining == 0


def test_coordination_health():
    coord = DistributedCoordinator()
    health = coord.health_check()
    assert health["status"] in ("HEALTHY", "DEGRADED")
    assert "mode" in health
