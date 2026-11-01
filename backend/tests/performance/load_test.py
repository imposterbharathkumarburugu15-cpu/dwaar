"""Automated Concurrent Load & Performance Benchmark Suite for PRAMANA.

Implements Module 13 of Phase 4:
- Concurrent simulated load across multiple synthetic institutions.
- Measures Requests per Second (RPS), p50, p95, p99 latency percentiles, and error rate.
- Tests multi-institution concurrent application processing and document pipeline execution.
"""

import concurrent.futures
from dataclasses import dataclass, field
import statistics
import time
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pramana.auth import hash_password
from pramana.db import Base, get_db
from pramana.main import app
from pramana.models import Application, Institution, User


@dataclass
class PerformanceBenchmarkResult:
    total_requests: int
    successful_requests: int
    failed_requests: int
    duration_seconds: float
    requests_per_second: float
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    error_rate_percent: float


def run_concurrent_workload(
    num_threads: int = 10,
    requests_per_thread: int = 20,
) -> PerformanceBenchmarkResult:
    """Executes concurrent simulated requests against PRAMANA API and computes latencies."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        # Seed test institutions & users
        for i in range(5):
            inst = Institution(id=f"INST-LOAD-{i}", aicte_id=f"1-LOAD-{i}", name=f"Engineering College {i}")
            user = User(
                id=f"u-load-{i}",
                username=f"inst_admin_{i}",
                role="institution_admin",
                institution_id=inst.id,
                display_name=f"Admin {i}",
                password_hash=hash_password("Pass@123"),
            )
            app_rec = Application(
                id=f"APP-LOAD-{i}",
                institution_id=inst.id,
                category="Engineering",
                academic_year="2026-27",
            )
            session.add_all([inst, user, app_rec])
        session.commit()

    def override_get_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    latencies_ms: list[float] = []
    success_count = 0
    failure_count = 0

    def worker_job(worker_id: int):
        nonlocal success_count, failure_count
        inst_idx = worker_id % 5
        # 1. Login
        r_login = client.post("/api/auth/login", json={"username": f"inst_admin_{inst_idx}", "password": "Pass@123"})
        csrf = r_login.json().get("csrf_token") if r_login.status_code == 200 else None
        headers = {"x-csrf-token": csrf} if csrf else {}

        local_latencies = []
        for req_idx in range(requests_per_thread):
            t0 = time.perf_counter()
            # Alternating endpoints: health check, metrics, task submission, pipeline query
            if req_idx % 3 == 0:
                resp = client.get("/api/v1/health")
            elif req_idx % 3 == 1:
                resp = client.get("/api/v1/metrics")
            else:
                resp = client.post(
                    f"/api/v1/applications/APP-LOAD-{inst_idx}/process",
                    headers=headers,
                    json={"priority": "normal"},
                )
            t_ms = (time.perf_counter() - t0) * 1000
            local_latencies.append(t_ms)
            if resp.status_code in (200, 201):
                success_count += 1
            else:
                failure_count += 1
        return local_latencies

    t_bench_start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker_job, i) for i in range(num_threads)]
        for f in concurrent.futures.as_completed(futures):
            latencies_ms.extend(f.result())

    total_time = time.perf_counter() - t_bench_start
    total_reqs = len(latencies_ms)
    sorted_latencies = sorted(latencies_ms)

    app.dependency_overrides.clear()

    return PerformanceBenchmarkResult(
        total_requests=total_reqs,
        successful_requests=success_count,
        failed_requests=failure_count,
        duration_seconds=round(total_time, 3),
        requests_per_second=round(total_reqs / total_time, 1) if total_time > 0 else 0.0,
        avg_latency_ms=round(statistics.mean(sorted_latencies), 2) if sorted_latencies else 0.0,
        p50_latency_ms=round(sorted_latencies[int(len(sorted_latencies) * 0.50)], 2) if sorted_latencies else 0.0,
        p95_latency_ms=round(sorted_latencies[int(len(sorted_latencies) * 0.95)], 2) if sorted_latencies else 0.0,
        p99_latency_ms=round(sorted_latencies[int(len(sorted_latencies) * 0.99)], 2) if sorted_latencies else 0.0,
        error_rate_percent=round((failure_count / total_reqs * 100), 2) if total_reqs > 0 else 0.0,
    )


if __name__ == "__main__":
    res = run_concurrent_workload(num_threads=10, requests_per_thread=20)
    print(f"Total Requests: {res.total_requests}")
    print(f"RPS: {res.requests_per_second} req/sec")
    print(f"Avg Latency: {res.avg_latency_ms} ms")
    print(f"p50: {res.p50_latency_ms} ms, p95: {res.p95_latency_ms} ms, p99: {res.p99_latency_ms} ms")
    print(f"Error Rate: {res.error_rate_percent}%")

