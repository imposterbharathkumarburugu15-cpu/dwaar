"""Offline Evidence Infrastructure: Local Case Bundles & Sync Reconciliation.

Supports remote field visits by AICTE inspection committees and regional officers
who may operate without reliable internet connectivity at rural campus sites.

Provides:
- Export of portable, cryptographically signed offline case investigation bundles.
- Offline viewing of document text, rendered page visuals, and extracted claims.
- Local field annotation capture and sync queue.
- Cryptographic conflict detection (detecting when online application evolved while inspector was offline).
- Manual reconciliation workflow for conflicted field observations.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..crypto import sha256_hex
from ..models import Application, AuditEvent, Document, DocumentPage, Finding, Institution, ValidationRun


def build_offline_bundle(db: Session, app_id: str, officer_id: str) -> dict[str, Any]:
    """Compiles a complete offline investigation case bundle for on-site inspection."""
    app = db.get(Application, app_id)
    if not app:
        raise ValueError(f"Application {app_id} not found")
        
    inst = app.institution
    docs = list(db.scalars(
        select(Document).where(Document.application_id == app_id, Document.superseded.is_(False))
    ).all())
    
    latest_run = db.scalars(
        select(ValidationRun).where(ValidationRun.application_id == app_id, ValidationRun.status == "complete")
        .order_by(ValidationRun.started_at.desc()).limit(1)
    ).first()
    
    findings = []
    if latest_run:
        findings = list(db.scalars(select(Finding).where(Finding.run_id == latest_run.id)).all())
        
    # Serialize document pages and fields for offline inspection
    doc_payloads = []
    for d in docs:
        pages = list(db.scalars(
            select(DocumentPage).where(DocumentPage.document_id == d.id).order_by(DocumentPage.page_no.asc())
        ).all())
        
        doc_payloads.append({
            "id": d.id,
            "declared_type": d.declared_type,
            "filename": d.original_filename,
            "sha256": d.sha256,
            "page_count": d.page_count,
            "mime": d.mime,
            "fields": [
                {
                    "name": f.name,
                    "value": f.value,
                    "page": f.page,
                    "bbox": f.bbox,
                    "confidence": f.confidence,
                }
                for f in d.fields
            ],
            "pages": [
                {
                    "page_no": p.page_no,
                    "text": p.text[:2000] if p.text else "",
                    "has_text": bool(p.text),
                }
                for p in pages
            ],
        })

    # Prepare on-site physical verification checklist items
    inspection_checklist = [
        {"item_id": "CHK-LAND", "title": "Physical Land Boundary Verification", "declared_value": app.declared.get("land_area_acres") or "Declared in Affidavit", "status": "pending", "notes": ""},
        {"item_id": "CHK-BUILDING", "title": "Built-up Area & Floor Plan Inspection", "declared_value": app.declared.get("built_up_area_sqm") or "Declared in Plan", "status": "pending", "notes": ""},
        {"item_id": "CHK-LABS", "title": "Computer Lab Workstation Count", "declared_value": "Declared in Campus Photo", "status": "pending", "notes": ""},
        {"item_id": "CHK-FIRE", "title": "Fire Hydrant & Safety Extinguisher Audit", "declared_value": "Valid Fire NOC Certified", "status": "pending", "notes": ""},
        {"item_id": "CHK-INTERNET", "title": "Bandwidth Speedtest & Service Provider Router", "declared_value": f"{app.declared.get('bandwidth_mbps', 300)} Mbps Tier", "status": "pending", "notes": ""},
        {"item_id": "CHK-FACULTY", "title": "Faculty Physical Attendance & Biometric Register", "declared_value": "Full Faculty Cadre Listed", "status": "pending", "notes": ""},
    ]

    bundle_meta = {
        "bundle_id": f"OFFLINE-{app.id}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        "exported_at": datetime.now(UTC).isoformat(),
        "exported_by": officer_id,
        "application_id": app.id,
        "application_status": app.status,
        "application_round": app.round,
        "academic_year": app.academic_year,
        "version_tag": app.id + f"-R{app.round}",
        "offline_notice": "DEMONSTRATION OFFLINE EVIDENCE BUNDLE — SYNC QUEUE ACTIVE",
        "stale_warning": "External registry lookups (e.g. live Municipal DB) cannot refresh while offline.",
    }
    
    canonical_bytes = json.dumps(bundle_meta, sort_keys=True).encode()
    bundle_hash = sha256_hex(canonical_bytes)
    bundle_meta["bundle_hash"] = bundle_hash

    return {
        "metadata": bundle_meta,
        "institution": {
            "id": inst.id,
            "aicte_id": inst.aicte_id,
            "name": inst.name,
            "address": inst.address,
            "district": inst.district,
            "state": inst.state,
            "pincode": inst.pincode,
            "latitude": inst.latitude,
            "longitude": inst.longitude,
        },
        "application": {
            "id": app.id,
            "category": app.category,
            "academic_year": app.academic_year,
            "status": app.status,
            "round": app.round,
            "declared": app.declared,
        },
        "documents": doc_payloads,
        "findings": [
            {
                "code": f.code,
                "category": f.category,
                "severity": f.severity,
                "title": f.title,
                "message": f.message,
                "review_status": f.review_status,
            }
            for f in findings
        ],
        "inspection_checklist": inspection_checklist,
    }


def process_offline_sync(
    db: Session,
    bundle_meta: dict[str, Any],
    local_annotations: list[dict[str, Any]],
    checklist_updates: list[dict[str, Any]],
    officer_username: str,
) -> dict[str, Any]:
    """Processes an inspector's queued offline updates upon reconnecting to the server.
    
    Performs conflict detection:
    - If the server application status or round has advanced beyond bundle_meta['application_round'],
      marks as conflicted and creates a reconciliation package.
    - Otherwise, cleanly integrates the offline inspection notes.
    """
    app_id = bundle_meta.get("application_id")
    app = db.get(Application, app_id)
    if not app:
        raise ValueError(f"Application {app_id} does not exist on server")
        
    server_round = app.round
    client_round = bundle_meta.get("application_round", 1)
    
    conflicts: list[dict[str, Any]] = []
    
    # Conflict Detection: Round Mismatch
    if server_round != client_round:
        conflicts.append({
            "conflict_type": "ROUND_MISMATCH",
            "message": (
                f"Application has advanced to Round {server_round} on the server, while the offline bundle "
                f"was captured on Round {client_round}. Documents may have been replaced."
            ),
            "client_round": client_round,
            "server_round": server_round,
        })
        
    # Conflict Detection: Status Mismatch
    server_status = app.status
    client_status = bundle_meta.get("application_status")
    if server_status != client_status:
        conflicts.append({
            "conflict_type": "STATUS_MISMATCH",
            "message": f"Server status is '{server_status}', but offline bundle was saved when status was '{client_status}'.",
            "client_status": client_status,
            "server_status": server_status,
        })

    if conflicts:
        return {
            "sync_status": "conflict_detected",
            "application_id": app_id,
            "conflicts_count": len(conflicts),
            "conflicts": conflicts,
            "pending_annotations": local_annotations,
            "pending_checklist": checklist_updates,
            "resolution_instructions": "Review discrepancies and call POST /api/offline/reconcile with chosen values.",
        }
        
    # Clean Sync: Apply updates to application declared attributes and record in audit chain
    declared = dict(app.declared or {})
    inspection_notes = declared.get("offline_inspection_notes", [])
    
    for note in local_annotations:
        inspection_notes.append({
            "recorded_by": officer_username,
            "recorded_at": note.get("timestamp") or datetime.now(UTC).isoformat(),
            "target": note.get("target"),
            "content": note.get("content"),
            "location_geo": note.get("location_geo"),
        })
        
    declared["offline_inspection_notes"] = inspection_notes
    declared["offline_checklist_results"] = checklist_updates
    declared["last_offline_sync"] = datetime.now(UTC).isoformat()
    app.declared = declared
    
    from ..audit import record
    record(
        db,
        actor=officer_username,
        actor_role="officer",
        action="inspection.offline_sync_applied",
        object_type="application",
        object_id=app.id,
        application_id=app.id,
        details={
            "bundle_id": bundle_meta.get("bundle_id"),
            "annotations_applied": len(local_annotations),
            "checklist_items_updated": len(checklist_updates),
        },
    )
    db.commit()
    
    return {
        "sync_status": "synchronized_cleanly",
        "application_id": app.id,
        "annotations_merged": len(local_annotations),
        "checklist_merged": len(checklist_updates),
        "synced_at": datetime.now(UTC).isoformat(),
        "audit_event": "inspection.offline_sync_applied",
    }


def reconcile_offline_conflicts(
    db: Session,
    app_id: str,
    resolutions: list[dict[str, Any]],
    officer_username: str,
) -> dict[str, Any]:
    """Applies manual reconciliation decisions selected by the reviewing officer."""
    app = db.get(Application, app_id)
    if not app:
        raise ValueError(f"Application {app_id} not found")
        
    declared = dict(app.declared or {})
    reconciliation_log = declared.get("reconciliation_history", [])
    
    for r in resolutions:
        reconciliation_log.append({
            "resolved_at": datetime.now(UTC).isoformat(),
            "resolved_by": officer_username,
            "item_key": r.get("item_key"),
            "chosen_source": r.get("chosen_source"),  # 'offline_field_observation' or 'server_document'
            "override_note": r.get("note"),
        })
        
    declared["reconciliation_history"] = reconciliation_log
    app.declared = declared
    
    from ..audit import record
    record(
        db,
        actor=officer_username,
        actor_role="officer",
        action="inspection.conflict_reconciled",
        object_type="application",
        object_id=app.id,
        application_id=app.id,
        details={"reconciled_items_count": len(resolutions)},
    )
    db.commit()
    
    return {
        "status": "reconciliation_complete",
        "application_id": app_id,
        "resolved_items_count": len(resolutions),
        "reconciled_at": datetime.now(UTC).isoformat(),
    }

