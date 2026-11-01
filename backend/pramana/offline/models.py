"""Database models for PRAMANA Offline Field Scrutiny, Evidence Provenance, and Synchronization.

Registered by pramana.db.init_db.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from ..models import UTCDateTime, new_id, utcnow


class FieldInspectionCase(Base):
    """An authorized physical inspection case conducted on-site at an institution."""

    __tablename__ = "field_inspection_cases"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("ins"))
    case_number: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), index=True)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), index=True)
    assigned_officer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)

    # Status: draft, in_progress, completed, signed, synced, conflict_detected
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    scheduled_date: Mapped[str | None] = mapped_column(String(20))
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    # Structured physical checklist: list of dicts {item_id, title, declared_value, observed_value, status, notes}
    checklist: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    # Observations: list of dicts {timestamp, content, location_geo, recorded_by}
    observations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    # Summary and determination
    summary: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str | None] = mapped_column(String(40))  # approve, reject, rectify

    # Cryptographic signing
    report_digest: Mapped[str | None] = mapped_column(String(64))  # SHA-256 of canonical report JSON
    signature: Mapped[str | None] = mapped_column(Text)  # Base64-encoded Ed25519 signature
    signer_kid: Mapped[str | None] = mapped_column(String(60))  # Officer key ID
    signed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    signed_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # Canonical snapshot of signed report

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


class InspectionEvidence(Base):
    """Structured evidence item captured during field inspection with cryptographic provenance."""

    __tablename__ = "inspection_evidence"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("evd"))
    inspection_id: Mapped[str] = mapped_column(ForeignKey("field_inspection_cases.id"), index=True)
    institution_id: Mapped[str] = mapped_column(String(40), index=True)
    officer_id: Mapped[str] = mapped_column(String(40), index=True)

    # Device-generated event identifier for sync idempotency
    device_event_id: Mapped[str] = mapped_column(String(64), index=True)

    # Category: document, image, inspection_note, supporting_attachment
    category: Mapped[str] = mapped_column(String(40), index=True)
    file_reference: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    phash: Mapped[str | None] = mapped_column(String(64))
    dhash: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text)

    # Metadata: device hardware info, authorized geo-coords, mime type, file size
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # Verification: unverified, verified_valid, duplicate_flagged, tamper_flagged
    verification_status: Mapped[str] = mapped_column(String(40), default="unverified")
    # Signature: unsigned, signed_by_officer
    signature_status: Mapped[str] = mapped_column(String(40), default="unsigned")

    collected_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class OfflineSyncEvent(Base):
    """Durable synchronization queue event with idempotency and conflict tracking."""

    __tablename__ = "offline_sync_events"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("syx"))
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # Client device UUID
    inspection_id: Mapped[str | None] = mapped_column(String(40), index=True)
    application_id: Mapped[str] = mapped_column(String(40), index=True)
    officer_id: Mapped[str] = mapped_column(String(40), index=True)

    # Event types: inspection_created, evidence_collected, report_signed, checklist_updated, manual_reconcile
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)

    # Status: pending, synchronized, conflict_detected, requires_review, resolved, rejected
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    conflict_type: Mapped[str | None] = mapped_column(String(60))
    conflict_details: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    resolution: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    receipt_id: Mapped[str | None] = mapped_column(String(64), index=True)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class OfflineRevocationCache(Base):
    """Local snapshot of revoked credentials for offline validation with explicit TTL warnings."""

    __tablename__ = "offline_revocation_cache"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("rev"))
    token_jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=True)
    revocation_reason: Mapped[str] = mapped_column(String(120), default="Unspecified")
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_sync_timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

