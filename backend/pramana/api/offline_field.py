"""FastAPI router for PRAMANA Field Scrutiny, Evidence Provenance, Signing, and Sync.

Mounts under /api/offline.
"""

import base64
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record
from ..auth import OFFICIAL_ROLES, User, current_user, require_roles
from ..db import get_db
from ..models import Application, Institution
from ..offline.evidence import detect_evidence_duplicates, record_field_evidence
from ..offline.models import FieldInspectionCase, InspectionEvidence, OfflineRevocationCache, OfflineSyncEvent
from ..offline.qr_verifier import verify_qr_offline
from ..offline.signing import default_keystore
from ..offline.sync_engine import process_offline_event_batch, resolve_sync_conflict

router = APIRouter(prefix="/api/offline", tags=["offline-field"])

INSPECTION_OFFICER_ROLES = ("super_admin", "aicte_admin", "regional_officer", "officer")


# --- Pydantic Schemas ---

class CreateInspectionPayload(BaseModel):
    application_id: str
    case_number: str
    scheduled_date: str | None = None
    checklist: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    summary: str | None = None


class UpdateChecklistPayload(BaseModel):
    checklist: list[dict[str, Any]]
    observations: list[dict[str, Any]] = []
    summary: str | None = None


class AttachEvidencePayload(BaseModel):
    category: str
    file_reference: str
    file_content_b64: str
    mime_type: str
    description: str
    device_event_id: str | None = None
    location_geo: dict[str, Any] | None = None
    device_metadata: dict[str, Any] | None = None


class SignReportPayload(BaseModel):
    summary: str | None = None
    recommendation: str = "approve"  # approve, reject, rectify


class VerifyReportSignaturePayload(BaseModel):
    pass


class OfflineQrVerifyPayload(BaseModel):
    token_or_link: str
    include_revocation_cache: bool = True


class OfflineSyncBatchPayload(BaseModel):
    events: list[dict[str, Any]]
    bundle_metadata: dict[str, Any] | None = None


class ResolveConflictPayload(BaseModel):
    event_id: str
    decision: str  # RESOLVED or REJECTED
    resolution_notes: str


# --- Endpoints ---

@router.get("/inspections")
def list_inspections(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Lists field inspections with strict role-based data isolation."""
    q = select(FieldInspectionCase)
    if user.role in ("regional_officer", "officer"):
        # Officers see assigned cases
        q = q.where(FieldInspectionCase.assigned_officer_id == user.id)
    elif user.role in ("institution_admin", "institution_operator", "applicant"):
        # Institutions see only cases for their own institution
        q = q.where(FieldInspectionCase.institution_id == user.institution_id)
    elif user.role not in OFFICIAL_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access forbidden to field inspection cases")

    cases = list(db.scalars(q.order_by(FieldInspectionCase.created_at.desc())).all())
    return [
        {
            "id": c.id,
            "case_number": c.case_number,
            "application_id": c.application_id,
            "institution_id": c.institution_id,
            "assigned_officer_id": c.assigned_officer_id,
            "status": c.status,
            "scheduled_date": c.scheduled_date,
            "summary": c.summary,
            "recommendation": c.recommendation,
            "is_signed": bool(c.signature),
            "signed_at": c.signed_at.isoformat() if c.signed_at else None,
            "created_at": c.created_at.isoformat(),
        }
        for c in cases
    ]


@router.post("/inspections")
def create_field_inspection(
    body: CreateInspectionPayload,
    user: User = Depends(require_roles(*INSPECTION_OFFICER_ROLES)),
    db: Session = Depends(get_db),
):
    """Creates a new field inspection case for on-site institutional scrutiny."""
    app = db.get(Application, body.application_id)
    if not app:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Application {body.application_id} not found")

    existing = db.scalars(
        select(FieldInspectionCase).where(FieldInspectionCase.case_number == body.case_number)
    ).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Case number {body.case_number} already exists")

    # Default physical inspection checklist if none provided
    checklist = body.checklist or [
        {"item_id": "CHK-LAND", "title": "Physical Land Boundary Verification", "declared_value": app.declared.get("land_area_acres") or "Declared in Affidavit", "observed_value": "", "status": "pending", "notes": ""},
        {"item_id": "CHK-BUILDING", "title": "Built-up Area & Floor Plan Inspection", "declared_value": app.declared.get("built_up_area_sqm") or "Declared in Plan", "observed_value": "", "status": "pending", "notes": ""},
        {"item_id": "CHK-LABS", "title": "Computer Lab Workstation Count", "declared_value": "Declared in Campus Photo", "observed_value": "", "status": "pending", "notes": ""},
        {"item_id": "CHK-FIRE", "title": "Fire Hydrant & Safety Extinguisher Audit", "declared_value": "Valid Fire NOC Certified", "observed_value": "", "status": "pending", "notes": ""},
        {"item_id": "CHK-INTERNET", "title": "Bandwidth Speedtest & Service Provider Router", "declared_value": f"{app.declared.get('bandwidth_mbps', 300)} Mbps Tier", "observed_value": "", "status": "pending", "notes": ""},
        {"item_id": "CHK-FACULTY", "title": "Faculty Physical Attendance & Biometric Register", "declared_value": "Full Faculty Cadre Listed", "observed_value": "", "status": "pending", "notes": ""},
    ]

    insp = FieldInspectionCase(
        case_number=body.case_number,
        application_id=body.application_id,
        institution_id=app.institution_id,
        assigned_officer_id=user.id,
        status="draft",
        scheduled_date=body.scheduled_date or datetime.now(UTC).strftime("%Y-%m-%d"),
        checklist=checklist,
        observations=body.observations,
        summary=body.summary,
    )
    db.add(insp)
    db.commit()
    db.refresh(insp)

    record(
        db,
        actor=user.username,
        actor_role="officer",
        action="inspection.created",
        object_type="field_inspection",
        object_id=insp.id,
        application_id=app.id,
        details={"case_number": insp.case_number, "institution_id": insp.institution_id},
    )
    db.commit()

    return {
        "id": insp.id,
        "case_number": insp.case_number,
        "application_id": insp.application_id,
        "institution_id": insp.institution_id,
        "status": insp.status,
        "checklist": insp.checklist,
        "created_at": insp.created_at.isoformat(),
    }


@router.get("/inspections/{inspection_id}")
def get_inspection_detail(
    inspection_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Retrieves full field inspection case details, checklist, and attached evidence."""
    insp = db.get(FieldInspectionCase, inspection_id)
    if not insp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Inspection {inspection_id} not found")

    if user.role not in OFFICIAL_ROLES and user.institution_id != insp.institution_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")

    evidence = list(db.scalars(
        select(InspectionEvidence).where(InspectionEvidence.inspection_id == inspection_id)
    ).all())

    return {
        "id": insp.id,
        "case_number": insp.case_number,
        "application_id": insp.application_id,
        "institution_id": insp.institution_id,
        "assigned_officer_id": insp.assigned_officer_id,
        "status": insp.status,
        "scheduled_date": insp.scheduled_date,
        "started_at": insp.started_at.isoformat() if insp.started_at else None,
        "completed_at": insp.completed_at.isoformat() if insp.completed_at else None,
        "checklist": insp.checklist,
        "observations": insp.observations,
        "summary": insp.summary,
        "recommendation": insp.recommendation,
        "is_signed": bool(insp.signature),
        "signature": insp.signature,
        "signer_kid": insp.signer_kid,
        "report_digest": insp.report_digest,
        "signed_at": insp.signed_at.isoformat() if insp.signed_at else None,
        "evidence_items": [
            {
                "id": e.id,
                "category": e.category,
                "file_reference": e.file_reference,
                "sha256": e.sha256,
                "phash": e.phash,
                "dhash": e.dhash,
                "description": e.description,
                "verification_status": e.verification_status,
                "signature_status": e.signature_status,
                "metadata": e.metadata_json,
                "collected_at": e.collected_at.isoformat(),
            }
            for e in evidence
        ],
    }


@router.post("/inspections/{inspection_id}/evidence")
def attach_field_evidence(
    inspection_id: str,
    body: AttachEvidencePayload,
    user: User = Depends(require_roles(*INSPECTION_OFFICER_ROLES)),
    db: Session = Depends(get_db),
):
    """Records a new evidence item with cryptographic hashing, duplicate detection, and provenance."""
    insp = db.get(FieldInspectionCase, inspection_id)
    if not insp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Inspection {inspection_id} not found")

    if insp.status == "signed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Inspection report is already digitally signed and locked against new evidence")

    try:
        file_bytes = base64.b64decode(body.file_content_b64)
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Base64 file content")

    evidence = record_field_evidence(
        db=db,
        inspection_id=inspection_id,
        institution_id=insp.institution_id,
        officer_id=user.username,
        category=body.category,
        file_reference=body.file_reference,
        file_bytes=file_bytes,
        mime_type=body.mime_type,
        description=body.description,
        device_event_id=body.device_event_id,
        location_geo=body.location_geo,
        device_metadata=body.device_metadata,
    )

    record(
        db,
        actor=user.username,
        actor_role="officer",
        action="inspection.evidence_collected",
        object_type="evidence",
        object_id=evidence.id,
        application_id=insp.application_id,
        details={
            "evidence_id": evidence.id,
            "category": evidence.category,
            "sha256": evidence.sha256,
            "verification_status": evidence.verification_status,
        },
    )
    db.commit()

    return {
        "id": evidence.id,
        "inspection_id": evidence.inspection_id,
        "sha256": evidence.sha256,
        "phash": evidence.phash,
        "dhash": evidence.dhash,
        "verification_status": evidence.verification_status,
        "duplicates_detected": evidence.metadata_json.get("duplicates", []),
        "collected_at": evidence.collected_at.isoformat(),
    }


@router.post("/inspections/{inspection_id}/sign")
def sign_inspection_report(
    inspection_id: str,
    body: SignReportPayload,
    user: User = Depends(require_roles(*INSPECTION_OFFICER_ROLES)),
    db: Session = Depends(get_db),
):
    """Digitally signs the field inspection report using an authorized Ed25519 officer key."""
    insp = db.get(FieldInspectionCase, inspection_id)
    if not insp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Inspection {inspection_id} not found")

    if insp.status == "signed":
        raise HTTPException(status.HTTP_409_CONFLICT, "Inspection report has already been signed")

    # Update summary and recommendation
    if body.summary:
        insp.summary = body.summary
    insp.recommendation = body.recommendation

    # Build canonical report payload to sign
    evidence = list(db.scalars(
        select(InspectionEvidence).where(InspectionEvidence.inspection_id == inspection_id)
    ).all())

    report_payload = {
        "case_number": insp.case_number,
        "application_id": insp.application_id,
        "institution_id": insp.institution_id,
        "officer_id": user.username,
        "checklist": insp.checklist,
        "observations": insp.observations,
        "summary": insp.summary,
        "recommendation": insp.recommendation,
        "evidence_hashes": sorted([e.sha256 for e in evidence]),
        "total_evidence_count": len(evidence),
    }

    signed_info = default_keystore.sign_report(report_payload, officer_id=user.username)

    insp.report_digest = signed_info["report_digest"]
    insp.signature = signed_info["signature"]
    insp.signer_kid = signed_info["signer_kid"]
    insp.signed_at = datetime.fromisoformat(signed_info["signed_at"])
    insp.signed_payload = report_payload
    insp.status = "signed"
    insp.completed_at = datetime.now(UTC)

    # Mark all evidence as signed by officer
    for e in evidence:
        e.signature_status = "signed_by_officer"

    record(
        db,
        actor=user.username,
        actor_role="officer",
        action="inspection.signed",
        object_type="field_inspection",
        object_id=insp.id,
        application_id=insp.application_id,
        details={
            "case_number": insp.case_number,
            "report_digest": insp.report_digest,
            "signer_kid": insp.signer_kid,
            "recommendation": insp.recommendation,
        },
    )
    db.commit()

    return {
        "status": "signed",
        "case_number": insp.case_number,
        "report_digest": insp.report_digest,
        "signature": insp.signature,
        "signer_kid": insp.signer_kid,
        "signed_at": insp.signed_at.isoformat(),
        "signer_public_key": signed_info["signer_public_key"],
    }


@router.post("/inspections/{inspection_id}/verify-signature")
def verify_report_signature(
    inspection_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Independently verifies the Ed25519 signature of an inspection report and detects tampering."""
    insp = db.get(FieldInspectionCase, inspection_id)
    if not insp:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Inspection {inspection_id} not found")

    if not insp.signature or not insp.signer_kid or not insp.report_digest:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Inspection report is not signed")

    # Reconstruct current report payload from live state
    evidence = list(db.scalars(
        select(InspectionEvidence).where(InspectionEvidence.inspection_id == inspection_id)
    ).all())

    current_report_payload = {
        "case_number": insp.case_number,
        "application_id": insp.application_id,
        "institution_id": insp.institution_id,
        "officer_id": user.username if user.role in OFFICIAL_ROLES else "authorized_officer",
        "checklist": insp.checklist,
        "observations": insp.observations,
        "summary": insp.summary,
        "recommendation": insp.recommendation,
        "evidence_hashes": sorted([e.sha256 for e in evidence]),
        "total_evidence_count": len(evidence),
    }

    # Verify against the signed snapshot
    payload_to_verify = insp.signed_payload or current_report_payload

    res = default_keystore.verify_report_signature(
        report_payload=payload_to_verify,
        expected_digest=insp.report_digest,
        signature_b64=insp.signature,
        signer_kid=insp.signer_kid,
    )

    return {
        "valid": res.valid,
        "signer_kid": res.signer_kid,
        "verified_at": res.verified_at,
        "digest_matches": res.digest_matches,
        "signature_matches": res.signature_matches,
        "error": res.error,
        "report_digest": res.report_digest,
    }


@router.post("/qr/verify")
def verify_offline_qr(
    body: OfflineQrVerifyPayload,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Verifies a signed QR token offline with clear separate revocation and expiry indicators."""
    revocation_cache: dict[str, Any] = {}
    if body.include_revocation_cache:
        # Load local revocation cache from database
        revoked_items = list(db.scalars(select(OfflineRevocationCache)).all())
        revocation_cache = {
            "last_sync_timestamp": datetime.now(UTC).isoformat(),
            "revoked_items": {
                r.token_jti: {"reason": r.revocation_reason, "revoked_at": r.revoked_at.isoformat() if r.revoked_at else None}
                for r in revoked_items
            },
        }

    res = verify_qr_offline(
        token_or_link=body.token_or_link,
        revocation_cache=revocation_cache if body.include_revocation_cache else None,
    )
    return {
        "status": res.status,
        "signature_valid": res.signature_valid,
        "expired": res.expired,
        "issuer_known": res.issuer_known,
        "revocation_status": res.revocation_status,
        "kid": res.kid,
        "issuer": res.issuer,
        "payload": res.payload,
        "error": res.error,
        "verified_at": res.verified_at,
        "offline_revocation_notice": res.offline_revocation_notice,
        "last_sync_timestamp": res.last_sync_timestamp,
    }


@router.post("/sync/batch")
def sync_offline_batch(
    body: OfflineSyncBatchPayload,
    user: User = Depends(require_roles(*INSPECTION_OFFICER_ROLES)),
    db: Session = Depends(get_db),
):
    """Ingests an offline event queue with strict idempotency, conflict detection, and receipts."""
    return process_offline_event_batch(
        db=db,
        officer_id=user.username,
        events=body.events,
        bundle_metadata=body.bundle_metadata,
    )


@router.post("/sync/resolve")
def resolve_offline_conflict(
    body: ResolveConflictPayload,
    user: User = Depends(require_roles(*INSPECTION_OFFICER_ROLES)),
    db: Session = Depends(get_db),
):
    """Resolves an offline synchronization conflict with an official officer determination."""
    return resolve_sync_conflict(
        db=db,
        event_id=body.event_id,
        officer_id=user.username,
        decision=body.decision,
        resolution_notes=body.resolution_notes,
    )
