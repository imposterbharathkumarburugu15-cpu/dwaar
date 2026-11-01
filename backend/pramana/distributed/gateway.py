"""API Gateway, Rate Limiting, Health, Tasks & Observability Endpoints.

Implements Module 7 of Phase 4:
- Mounts under `/api/v1`.
- Request ID propagation and telemetry tracking.
- Health, readiness, Prometheus metrics, and infrastructure status endpoints.
- Asynchronous task dispatching, status polling, and retry triggers.
- Multi-institution tenant-isolated document upload and retrieval.
"""

import base64
from datetime import UTC, datetime
import time
from typing import Any
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import User, current_user, require_roles
from ..db import get_db, check_db_health
from .models import DocumentPipelineStageRecord, StorageObjectRecord, TaskExecutionRecord
from .observability import metrics_collector
from .redis_client import default_coordinator
from .storage import default_storage
from .tasks import process_document_pipeline_task, scrutinize_application_async_task

router = APIRouter(prefix="/api/v1", tags=["distributed-infrastructure"])


# --- Payloads ---

class ProcessApplicationPayload(BaseModel):
    priority: str = "normal"


class RetryTaskPayload(BaseModel):
    force: bool = False


class DirectUploadPayload(BaseModel):
    original_filename: str
    content_type: str = "application/pdf"
    file_bytes_b64: str
    document_id: str | None = None
    application_id: str | None = None


# --- Health & Observability Endpoints ---

@router.get("/health")
def get_system_health():
    """Liveness probe: verifies basic process execution and database connection."""
    db_status = check_db_health()
    is_healthy = db_status.get("status") == "HEALTHY"
    return {
        "status": "UP" if is_healthy else "DOWN",
        "timestamp": datetime.now(UTC).isoformat(),
        "database": db_status,
        "coordination": default_coordinator.health_check(),
    }


@router.get("/ready")
def get_system_readiness():
    """Readiness probe: validates readiness to accept incoming traffic."""
    db_status = check_db_health()
    redis_status = default_coordinator.health_check()
    is_ready = db_status.get("connected", False)

    if not is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="System not ready: database connection unavailable",
        )

    return {
        "status": "READY",
        "timestamp": datetime.now(UTC).isoformat(),
        "database_ready": True,
        "coordinator_mode": redis_status.get("mode"),
    }


@router.get("/metrics")
def get_prometheus_metrics():
    """Prometheus exposition format metrics scraper endpoint."""
    metrics_text = metrics_collector.generate_prometheus_metrics()
    return Response(content=metrics_text, media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/infrastructure/status")
def get_infrastructure_status(
    user: User = Depends(current_user),
):
    """Structured telemetry summary for administrators and observability dashboards."""
    return metrics_collector.get_summary_dict()


# --- Asynchronous Task & Processing Endpoints ---

@router.post("/applications/{application_id}/process")
def dispatch_application_processing(
    application_id: str,
    body: ProcessApplicationPayload,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Dispatches asynchronous application scrutiny to the Celery worker queue."""
    # Tenant verification
    inst_id = user.institution_id or "INST-AICTE"
    if user.role in ("institution_admin", "institution_operator", "applicant") and user.institution_id:
        from ..models import Application
        app = db.get(Application, application_id)
        if not app or app.institution_id != user.institution_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied: application belongs to another institution")

    task = scrutinize_application_async_task.delay(
        application_id=application_id,
        institution_id=inst_id,
        operator=user.username,
    )
    metrics_collector.record_task_dispatched("scrutinize_application_async", "ai_verification")

    return {
        "task_id": task.id,
        "status": "DISPATCHED",
        "application_id": application_id,
        "queue": "ai_verification",
        "dispatched_at": datetime.now(UTC).isoformat(),
    }


@router.get("/tasks/{task_id}")
def get_task_status(
    task_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Retrieves asynchronous task status, progress, duration, and results."""
    rec = db.get(TaskExecutionRecord, task_id)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Task '{task_id}' not found")

    # Multi-tenant isolation: institution users cannot inspect another institution's task
    if (
        user.role in ("institution_admin", "institution_operator", "applicant")
        and user.institution_id
        and rec.institution_id
        and rec.institution_id != user.institution_id
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied: Task belongs to another institution")

    return {
        "task_id": rec.task_id,
        "task_name": rec.task_name,
        "queue": rec.queue,
        "status": rec.status,
        "institution_id": rec.institution_id,
        "created_at": rec.created_at.isoformat(),
        "started_at": rec.started_at.isoformat() if rec.started_at else None,
        "completed_at": rec.completed_at.isoformat() if rec.completed_at else None,
        "duration_ms": rec.duration_ms,
        "retries_count": rec.retries_count,
        "result": rec.result_json,
        "error": rec.error_message,
    }


@router.post("/tasks/{task_id}/retry")
def retry_failed_task(
    task_id: str,
    body: RetryTaskPayload,
    user: User = Depends(require_roles("super_admin", "aicte_admin", "admin", "regional_officer")),
    db: Session = Depends(get_db),
):
    """Allows authorized regulatory officers to retry a failed background task."""
    rec = db.get(TaskExecutionRecord, task_id)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Task '{task_id}' not found")

    if rec.status != "FAILED" and not body.force:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Cannot retry task in '{rec.status}' status (must be FAILED)")

    rec.status = "RETRYING"
    rec.retries_count += 1
    db.commit()

    # Re-dispatch based on task_name
    if rec.task_name == "scrutinize_application_async":
        new_task = scrutinize_application_async_task.delay(
            application_id=rec.payload_json.get("application_id"),
            institution_id=rec.institution_id or "INST-AICTE",
            operator=user.username,
        )
        return {"status": "RE_DISPATCHED", "new_task_id": new_task.id}

    return {"status": "MARKED_RETRYING", "task_id": task_id}


@router.get("/applications/{application_id}/processing-status")
def get_application_pipeline_status(
    application_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Retrieves 12-stage pipeline progress and document validation status."""
    if user.role in ("institution_admin", "institution_operator", "applicant") and user.institution_id:
        from ..models import Application
        app = db.get(Application, application_id)
        if not app or app.institution_id != user.institution_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")

    stages = list(
        db.scalars(
            select(DocumentPipelineStageRecord)
            .where(DocumentPipelineStageRecord.application_id == application_id)
            .order_by(DocumentPipelineStageRecord.stage_index.asc())
        ).all()
    )

    stage_list = [
        {
            "stage_id": s.id,
            "stage_name": s.stage_name,
            "stage_index": s.stage_index,
            "status": s.status,
            "duration_ms": s.duration_ms,
            "error": s.error_message,
        }
        for s in stages
    ]

    total_stages = len(stage_list)
    completed_stages = sum(1 for s in stage_list if s["status"] == "COMPLETED")
    progress_percent = round((completed_stages / total_stages * 100), 1) if total_stages > 0 else 0.0

    return {
        "application_id": application_id,
        "stages": stage_list,
        "completed_count": completed_stages,
        "total_stages": total_stages,
        "progress_percent": progress_percent,
        "is_complete": completed_stages == total_stages and total_stages > 0,
    }


# --- Object Storage Endpoints ---

@router.post("/storage/upload")
def upload_storage_document(
    body: DirectUploadPayload,
    user: User = Depends(current_user),
):
    """Direct multi-institution document upload to the object storage layer."""
    inst_id = user.institution_id or "INST-SYSTEM"
    try:
        raw_bytes = base64.b64decode(body.file_bytes_b64)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed base64 file data")

    key = f"{inst_id}/{uuid.uuid4().hex[:12]}_{body.original_filename}"
    try:
        rec = default_storage.upload(
            file_bytes=raw_bytes,
            object_key=key,
            original_filename=body.original_filename,
            content_type=body.content_type,
            institution_id=inst_id,
            uploaded_by=user.username,
        )
        return {
            "object_id": rec.object_id,
            "object_key": rec.object_key,
            "byte_size": rec.byte_size,
            "sha256": rec.sha256_checksum,
            "institution_id": rec.institution_id,
        }
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err))
    except PermissionError as err:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(err))


@router.get("/storage/documents/{object_key:path}")
def download_storage_document(
    object_key: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Retrieves document from object store with strict tenant isolation."""
    inst_filter = user.institution_id if user.role in ("institution_admin", "institution_operator", "applicant") else None
    try:
        data = default_storage.download(object_key, institution_id=inst_filter)
        meta = default_storage.get_metadata(object_key)
        return Response(content=data, media_type=meta.get("content_type", "application/pdf"))
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    except PermissionError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied: Document belongs to another institution")

