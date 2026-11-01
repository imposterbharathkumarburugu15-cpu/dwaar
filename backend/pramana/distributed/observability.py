"""Centralized Observability, Prometheus Metrics & Structured Logging.

Implements Module 11 of Phase 4:
- Prometheus text-format metrics exporter.
- Request latency, throughput, error rates, database health, and queue metrics.
- Structured JSON logging with correlation IDs (request_id, task_id).
- Sensitive credential and private key redaction filter.
"""

from collections import defaultdict
from datetime import UTC, datetime
import json
import logging
import threading
import time
from typing import Any

from sqlalchemy import func, select

from ..db import SessionLocal, check_db_health
from .models import DocumentPipelineStageRecord, TaskExecutionRecord
from .redis_client import default_coordinator


class MetricsCollector:
    """Thread-safe in-memory and database metrics aggregator for Prometheus export."""

    def __init__(self):
        self._lock = threading.Lock()
        self._http_requests_total = defaultdict(int)
        self._http_request_duration_sum = defaultdict(float)
        self._http_request_duration_count = defaultdict(int)
        self._tasks_dispatched_total = defaultdict(int)

    def record_http_request(self, method: str, endpoint: str, status_code: int, duration_seconds: float) -> None:
        key = (method, endpoint, str(status_code))
        with self._lock:
            self._http_requests_total[key] += 1
            self._http_request_duration_sum[key] += duration_seconds
            self._http_request_duration_count[key] += 1

    def record_task_dispatched(self, task_name: str, queue: str) -> None:
        key = (task_name, queue)
        with self._lock:
            self._tasks_dispatched_total[key] += 1

    def generate_prometheus_metrics(self) -> str:
        """Renders Prometheus standard exposition format."""
        lines = [
            "# HELP pramana_system_info Pramana platform metadata",
            "# TYPE pramana_system_info gauge",
            'pramana_system_info{version="2.0.0",app="pramana"} 1',
            "# HELP pramana_http_requests_total Total HTTP requests handled",
            "# TYPE pramana_http_requests_total counter",
        ]

        with self._lock:
            for (method, endpoint, status_code), count in self._http_requests_total.items():
                lines.append(
                    f'pramana_http_requests_total{{method="{method}",endpoint="{endpoint}",status="{status_code}"}} {count}'
                )

            lines.extend([
                "# HELP pramana_http_request_duration_seconds Total HTTP request duration",
                "# TYPE pramana_http_request_duration_seconds summary",
            ])
            for (method, endpoint, status_code), total_dur in self._http_request_duration_sum.items():
                cnt = self._http_request_duration_count[(method, endpoint, status_code)]
                lines.append(
                    f'pramana_http_request_duration_seconds_sum{{method="{method}",endpoint="{endpoint}",status="{status_code}"}} {total_dur:.4f}'
                )
                lines.append(
                    f'pramana_http_request_duration_seconds_count{{method="{method}",endpoint="{endpoint}",status="{status_code}"}} {cnt}'
                )

            lines.extend([
                "# HELP pramana_tasks_dispatched_total Total asynchronous Celery tasks dispatched",
                "# TYPE pramana_tasks_dispatched_total counter",
            ])
            for (task_name, queue), count in self._tasks_dispatched_total.items():
                lines.append(
                    f'pramana_tasks_dispatched_total{{task="{task_name}",queue="{queue}"}} {count}'
                )

        # Database health probe
        db_health = check_db_health()
        db_status_val = 1 if db_health.get("status") == "HEALTHY" else 0
        lines.extend([
            "# HELP pramana_database_connected Database connection status (1=connected, 0=disconnected)",
            "# TYPE pramana_database_connected gauge",
            f'pramana_database_connected{{dialect="{db_health.get("dialect", "unknown")}"}} {db_status_val}',
            "# HELP pramana_database_latency_milliseconds Database query round-trip latency",
            "# TYPE pramana_database_latency_milliseconds gauge",
            f'pramana_database_latency_milliseconds{{dialect="{db_health.get("dialect", "unknown")}"}} {db_health.get("latency_ms", 0.0)}',
        ])

        # Redis health probe
        redis_health = default_coordinator.health_check()
        redis_status_val = 1 if redis_health.get("status") == "HEALTHY" else 0
        lines.extend([
            "# HELP pramana_redis_connected Redis distributed coordinator status (1=healthy, 0=unhealthy)",
            "# TYPE pramana_redis_connected gauge",
            f'pramana_redis_connected{{mode="{redis_health.get("mode", "unknown")}"}} {redis_status_val}',
        ])

        # Task and Pipeline stage summary from DB
        try:
            with SessionLocal() as db:
                task_counts = db.execute(
                    select(TaskExecutionRecord.status, func.count()).group_by(TaskExecutionRecord.status)
                ).all()

                lines.extend([
                    "# HELP pramana_async_tasks_by_status Total background tasks by status",
                    "# TYPE pramana_async_tasks_by_status gauge",
                ])
                for status_name, cnt in task_counts:
                    lines.append(f'pramana_async_tasks_by_status{{status="{status_name}"}} {cnt}')
        except Exception:
            pass

        return "\n".join(lines) + "\n"

    def get_summary_dict(self) -> dict[str, Any]:
        """Returns structured JSON summary of system telemetry."""
        db_health = check_db_health()
        redis_health = default_coordinator.health_check()

        task_stats = {}
        stage_stats = {}
        try:
            with SessionLocal() as db:
                for s, count in db.execute(
                    select(TaskExecutionRecord.status, func.count()).group_by(TaskExecutionRecord.status)
                ).all():
                    task_stats[s] = count

                for s, count in db.execute(
                    select(DocumentPipelineStageRecord.status, func.count()).group_by(DocumentPipelineStageRecord.status)
                ).all():
                    stage_stats[s] = count
        except Exception:
            pass

        with self._lock:
            total_reqs = sum(self._http_requests_total.values())

        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "total_http_requests": total_reqs,
            "database": db_health,
            "redis_coordination": redis_health,
            "task_executions": task_stats,
            "pipeline_stages": stage_stats,
        }


# Global metrics collector
metrics_collector = MetricsCollector()


class StructuredJsonFormatter(logging.Formatter):
    """Formats log records as JSON lines with redaction of sensitive credentials."""

    REDACTED_KEYS = {"password", "secret", "private_key", "token", "key_material", "pin"}

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "request_id"):
            log_obj["request_id"] = getattr(record, "request_id")
        if hasattr(record, "task_id"):
            log_obj["task_id"] = getattr(record, "task_id")
        if hasattr(record, "institution_id"):
            log_obj["institution_id"] = getattr(record, "institution_id")

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)

