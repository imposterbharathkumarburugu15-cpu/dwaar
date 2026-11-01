"""Tests for Outbound External API Security Gateway (SSRF, Circuit Breaker, Redaction)."""

import pytest
from pramana.integrations.gateway import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    ExternalAPISecurityGateway,
    SSRFValidationError,
)


def test_ssrf_validation_allowed_domain():
    gateway = ExternalAPISecurityGateway(allow_local_for_tests=False)
    host = gateway.validate_destination_url("https://sandbox.apisetu.gov.in/v1/test")
    assert host == "sandbox.apisetu.gov.in"


def test_ssrf_validation_blocked_unapproved_domain():
    gateway = ExternalAPISecurityGateway(allow_local_for_tests=False)
    with pytest.raises(SSRFValidationError):
        gateway.validate_destination_url("https://malicious-attacker-server.com/exfiltrate")


def test_sensitive_header_scrubbing():
    gateway = ExternalAPISecurityGateway()
    raw_headers = {
        "Authorization": "Bearer secret_token_xyz",
        "X-APISETU-APIKEY": "super_secret_key_123",
        "Content-Type": "application/json",
        "User-Agent": "Pramana/2.0",
    }
    scrubbed = gateway.scrub_headers(raw_headers)
    assert scrubbed["Authorization"] == "[REDACTED]"
    assert scrubbed["X-APISETU-APIKEY"] == "[REDACTED]"
    assert scrubbed["Content-Type"] == "application/json"


def test_circuit_breaker_transitions():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout_sec=0.1)
    assert cb.can_execute() is True
    assert cb.state == "CLOSED"

    # Record 3 failures to trip breaker
    cb.record_failure()
    cb.record_failure()
    assert cb.state == "CLOSED"
    cb.record_failure()
    assert cb.state == "OPEN"
    assert cb.can_execute() is False

    # Simulate recovery wait
    import time
    time.sleep(0.15)
    assert cb.can_execute() is True  # Transitions to HALF_OPEN
    assert cb.state == "HALF_OPEN"

    # Successful call closes breaker
    cb.record_success()
    assert cb.state == "CLOSED"

