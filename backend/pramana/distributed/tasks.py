"""Asynchronous Celery Tasks with Idempotency, Retries & Auditable State Tracking."""

from datetime import UTC, datetime
import logging
import time
import traceback
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record
from ..db import SessionLocal, get_db
from .celery_app import celery_app
from .models import TaskExecutionRecord

logger = logging.getLogger("pramana.distributed.tasks")


def get_task_db() -> Session:
    """Returns a database session respecting active dependency overrides if present."""
    from ..main import app

    if get_db in app.dependency_overrides:
        gen = app.dependency_overrides[get_db]()
        return next(gen)
    return SessionLocal()


def init_task_record(
    task_id: str,
    task_name: str,
    queue: str,
    payload: dict[str, Any],
    institution_id: str | None = None,
    initiated_by: str | None = None,
) -> TaskExecutionRecord:
    """Initializes a new TaskExecutionRecord before task execution."""
    with get_task_db() as db:
        existing = db.get(TaskExecutionRecord, task_id)
        if existing:
            return existing
        rec = TaskExecutionRecord(
            task_id=task_id,
            task_name=task_name,
            queue=queue,
            status="PENDING",
            institution_id=institution_id,
            initiated_by=initiated_by,
            payload_json=payload,
            created_at=datetime.now(UTC),
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return rec


def update_task_state(
    task_id: str,
    status: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
    tb: str | None = None,
    duration_ms: float | None = None,
) -> None:
    """Updates database record for task execution."""
    with get_task_db() as db:
        rec = db.get(TaskExecutionRecord, task_id)
        if not rec:
            return
        rec.status = status
        now = datetime.now(UTC)
        if status == "RUNNING" and not rec.started_at:
            rec.started_at = now
        elif status in ("COMPLETED", "FAILED", "CANCELLED"):
            rec.completed_at = now
            if duration_ms is not None:
                rec.duration_ms = duration_ms
            elif rec.started_at:
                rec.duration_ms = round((now - rec.started_at).total_seconds() * 1000, 2)
        if result is not None:
            rec.result_json = result
        if error:
            rec.error_message = error
        if tb:
            rec.error_traceback = tb
        db.commit()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=5)
def process_document_pipeline_task(
    self,
    document_id: str,
    application_id: str,
    institution_id: str,
    file_bytes_b64: str | None = None,
    operator: str = "celery_worker",
) -> dict[str, Any]:
    """Asynchronous Document Processing Pipeline Task."""
    task_id = self.request.id or f"task_{document_id}"
    t0 = time.perf_counter()

    # Idempotency check: if already completed, return existing result
    with get_task_db() as db:
        rec = db.get(TaskExecutionRecord, task_id)
        if not rec:
            rec = db.get(TaskExecutionRecord, f"task_{document_id}")
        if rec and rec.status == "COMPLETED" and rec.result_json:
            logger.info("Task %s already completed (idempotent skip)", rec.task_id)
            return rec.result_json

    init_task_record(
        task_id=task_id,
        task_name="process_document_pipeline",
        queue="document_processing",
        payload={"document_id": document_id, "application_id": application_id},
        institution_id=institution_id,
        initiated_by=operator,
    )
    update_task_state(task_id, "RUNNING")

    try:
        from .pipeline import default_document_pipeline

        # Execute 12-stage pipeline
        pipeline_result = default_document_pipeline.execute_pipeline(
            document_id=document_id,
            application_id=application_id,
            institution_id=institution_id,
            file_bytes_b64=file_bytes_b64,
        )

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        update_task_state(task_id, "COMPLETED", result=pipeline_result, duration_ms=elapsed_ms)
        return pipeline_result

    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        tb = traceback.format_exc()
        if self.request.retries < self.max_retries:
            update_task_state(task_id, "RETRYING", error=str(exc))
            raise self.retry(exc=exc)
        update_task_state(task_id, "FAILED", error=str(exc), tb=tb, duration_ms=elapsed_ms)
        raise exc


@celery_app.task(bind=True, max_retries=2, default_retry_delay=5)
def scrutinize_application_async_task(
    self,
    application_id: str,
    institution_id: str,
    operator: str = "celery_worker",
) -> dict[str, Any]:
    """Asynchronous Application Scrutiny & Regulatory Verification."""
    task_id = self.request.id or f"task_scrutiny_{application_id}"
    t0 = time.perf_counter()

    init_task_record(
        task_id=task_id,
        task_name="scrutinize_application_async",
        queue="ai_verification",
        payload={"application_id": application_id},
        institution_id=institution_id,
        initiated_by=operator,
    )
    update_task_state(task_id, "RUNNING")

    try:
        from ..engine import evaluate

        with get_task_db() as db:
            run_record = evaluate(db, application_id, actor=operator)
            res = {
                "run_id": run_record.id,
                "status": run_record.status,
                "outcome": run_record.outcome,
                "findings_count": len(run_record.findings),
            }

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        update_task_state(task_id, "COMPLETED", result=res, duration_ms=elapsed_ms)
        return res

    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        tb = traceback.format_exc()
        if self.request.retries < self.max_retries:
            update_task_state(task_id, "RETRYING", error=str(exc))
            raise self.retry(exc=exc)
        update_task_state(task_id, "FAILED", error=str(exc), tb=tb, duration_ms=elapsed_ms)
        raise exc


@celery_app.task(bind=True, max_retries=1)
def verify_certificate_async_task(
    self,
    cert_pem: str,
    environment: str = "development",
) -> dict[str, Any]:
    """Asynchronous PKI Certificate Validation."""
    task_id = self.request.id or f"task_cert_{int(time.time()*1000)}"
    t0 = time.perf_counter()

    init_task_record(
        task_id=task_id,
        task_name="verify_certificate_async",
        queue="certificate_verification",
        payload={"environment": environment},
    )
    update_task_state(task_id, "RUNNING")

    try:
        from ..trust.certificates import validate_certificate

        with get_task_db() as db:
            result = validate_certificate(db, cert_pem, environment=environment)
            res = {
                "valid": result.valid,
                "status": result.status,
                "subject_dn": result.subject_dn,
                "serial_number": result.serial_number,
                "days_until_expiry": result.days_until_expiry,
                "error": result.error,
            }

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        update_task_state(task_id, "COMPLETED", result=res, duration_ms=elapsed_ms)
        return res

    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        update_task_state(task_id, "FAILED", error=str(exc), duration_ms=elapsed_ms)
        raise exc

