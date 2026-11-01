"""Unit & Integration tests for Distributed API Gateway, Observability & Health Probes (Module 7 & 11)."""

import pytest
from fastapi.testclient import TestClient
from pramana.main import app
from pramana.distributed.observability import metrics_collector


def test_gateway_health_and_readiness_endpoints():
    client = TestClient(app)

    # Liveness probe
    r_health = client.get("/api/v1/health")
    assert r_health.status_code == 200
    data = r_health.json()
    assert data["status"] in ("UP", "DOWN", "HEALTHY", "DEGRADED")
    assert "database" in data
    assert "coordination" in data
    assert "timestamp" in data

    # Readiness probe
    r_ready = client.get("/api/v1/ready")
    assert r_ready.status_code == 200
    assert r_ready.json()["status"] == "READY"
    assert r_ready.json()["database_ready"] is True


def test_prometheus_metrics_export():
    client = TestClient(app)

    # Perform a request to generate metrics
    client.get("/api/v1/health")

    r_metrics = client.get("/api/v1/metrics")
    assert r_metrics.status_code == 200
    body = r_metrics.text
    assert "# HELP pramana_http_requests_total" in body
    assert "# TYPE pramana_http_requests_total counter" in body
    assert "pramana_system_info" in body


def test_request_correlation_id_propagation():
    client = TestClient(app)
    custom_cid = "req_custom_trace_987654321"

    resp = client.get("/api/v1/health", headers={"x-correlation-id": custom_cid})
    assert resp.status_code == 200
    assert resp.headers.get("x-correlation-id") == custom_cid
