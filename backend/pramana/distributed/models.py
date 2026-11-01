"""Database Models for Distributed Infrastructure, Pipelines & Tasks."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base
from ..models import UTCDateTime, utcnow


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class TaskExecutionRecord(Base):
    """Tracks asynchronous Celery and background job execution states."""

    __tablename__ = "task_execution_records"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_name: Mapped[str] = mapped_column(String(128), index=True)
    queue: Mapped[str] = mapped_column(String(64), default="default", index=True)
    status: Mapped[str] = mapped_column(
        String(32), default="PENDING", index=True
    )  # PENDING, RUNNING, COMPLETED, FAILED, RETRYING, CANCELLED
    institution_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    initiated_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
    retries_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)


class DocumentPipelineStageRecord(Base):
    """Tracks stage-level execution across the 12-stage Document Processing Pipeline."""

    __tablename__ = "document_pipeline_stages"

    id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("stg"))
    document_id: Mapped[str] = mapped_column(String(40), index=True)
    application_id: Mapped[str] = mapped_column(String(40), index=True)
    institution_id: Mapped[str] = mapped_column(String(40), index=True)
    stage_name: Mapped[str] = mapped_column(String(64), index=True)
    # Stage Names:
    # DOCUMENT_UPLOADED, DOCUMENT_VALIDATION, FILE_TYPE_VERIFICATION,
    # MALWARE_SCAN_ADAPTER, OCR_EXTRACTION, TEXT_NORMALIZATION,
    # DOCUMENT_FINGERPRINTING, FORENSIC_ANALYSIS, FACT_EXTRACTION,
    # REGULATORY_RULE_VALIDATION, RISK_SCORING, FINAL_SCRUTINY_RESULT
    stage_index: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(
        String(32), default="PENDING", index=True
    )  # PENDING, PROCESSING, COMPLETED, FAILED, SKIPPED
    input_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stage_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)


class StorageObjectRecord(Base):
    """Catalog of durable objects managed by the Object Storage Abstraction layer."""

    __tablename__ = "storage_objects"

    object_id: Mapped[str] = mapped_column(String(48), primary_key=True, default=lambda: new_id("obj"))
    storage_provider: Mapped[str] = mapped_column(String(32), default="LOCAL")  # LOCAL, S3, GCS
    bucket_name: Mapped[str] = mapped_column(String(128), default="pramana-documents")
    object_key: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    original_filename: Mapped[str] = mapped_column(String(256))
    content_type: Mapped[str] = mapped_column(String(128), default="application/pdf")
    byte_size: Mapped[int] = mapped_column(Integer, default=0)
    sha256_checksum: Mapped[str] = mapped_column(String(64), index=True)
    uploaded_by: Mapped[str] = mapped_column(String(80), default="system")
    institution_id: Mapped[str] = mapped_column(String(40), index=True)
    uploaded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    is_encrypted: Mapped[bool] = mapped_column(Boolean, default=True)
    encryption_algorithm: Mapped[str] = mapped_column(String(32), default="AES_256_GCM")
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)

