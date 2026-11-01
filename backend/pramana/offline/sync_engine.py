"""Secure Synchronization & Conflict Resolution Engine for PRAMANA Field Scrutiny.

Implements Modules 5, 6, and 7 of Phase 2:
- Idempotent offline event batch ingestion.
- Durable sync queue processing.
- Multi-scenario conflict detection:
  * CONCURRENT_OFFICER_EDIT
  * INSTITUTION_EVIDENCE_REPLACED
  * SIGNED_REPORT_EVIDENCE_ALTERED
  * DUPLICATE_OR_RETRY
- Explicit conflict states:
  * PENDING_SYNC, SYNCHRONIZED, CONFLICT_DETECTED, REQUIRES_OFFICER_REVIEW, RESOLVED, REJECTED
- Tamper-evident Merkle audit trail integration with Ed25519 checkpointing.
- Verifiable synchronization receipts.
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record, verify_chain
from ..crypto import sha256_hex
from ..models import Application, AuditEvent, Document, Institution, User
from .evidence import record_field_evidence
from .models import FieldInspectionCase, InspectionEvidence, OfflineSyncEvent
from .signing import default_keystore


def generate_sync_receipt(
    db: Session,
    receipt_id: str,
    officer_id: str,
    processed_count: int,
    conflicts_count: int,
) -> dict[str, Any]:
    """Generates an immutable, verifiable synchronization receipt bound to the Merkle audit head."""
    last_audit = db.scalars(
        select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(1)
    ).first()
    merkle_head = last_audit.hash if last_audit else "0" * 64
    seq_head = last_audit.seq if last_audit else 0

    receipt = {
        "receipt_id": receipt_id,
        "issued_at": datetime.now(UTC).isoformat(),
        "officer_id": officer_id,
        "events_processed": processed_count,
        "conflicts_detected": conflicts_count,
        "merkle_head_seq": seq_head,
        "merkle_head_hash": merkle_head,
        "receipt_signature": sha256_hex(f"{receipt_id}:{merkle_head}:{processed_count}".encode()),
    }
    return receipt


def process_offline_event_batch(
    db: Session,
    officer_id: str,
    events: list[dict[str, Any]],
    bundle_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ingests a batch of offline events with strict idempotency and conflict detection."""
    receipt_id = f"RCPT-{uuid.uuid4().hex[:12].upper()}"
    processed_events: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []

    for evt in events:
        event_id = evt.get("event_id") or evt.get("id") or str(uuid.uuid4())
        event_type = evt.get("event_type", "unknown")
        app_id = evt.get("application_id")
        insp_id = evt.get("inspection_id")
        payload = evt.get("payload", {})

        # 1. Idempotency Check: Prevent duplicate event processing
        existing_event = db.scalars(
            select(OfflineSyncEvent).where(OfflineSyncEvent.event_id == event_id)
        ).first()

        if existing_event:
            processed_events.append({
                "event_id": event_id,
                "status": "DUPLICATE_IGNORED",
                "message": "Event was already processed idempotently in a previous sync session",
                "receipt_id": existing_event.receipt_id,
            })
            continue

        app = db.get(Application, app_id) if app_id else None
        inspection = db.get(FieldInspectionCase, insp_id) if insp_id else None

        # Conflict Detection:
        conflict_detected: str | None = None
        conflict_info: dict[str, Any] = {}

        # Scenario 1: Signed Report Evidence Altered
        if inspection and inspection.status == "signed":
            if event_type in ("evidence_collected", "checklist_updated", "observations_added"):
                conflict_detected = "SIGNED_REPORT_EVIDENCE_ALTERED"
                conflict_info = {
                    "reason": "Inspection report is already digitally signed. Further evidence or checklist edits are locked.",
                    "inspection_id": inspection.id,
                    "case_number": inspection.case_number,
                    "signed_at": inspection.signed_at.isoformat() if inspection.signed_at else None,
                }

        # Scenario 2: Concurrent Server Status or Round Advancement
        if app and bundle_metadata:
            server_round = app.round
            client_round = bundle_metadata.get("application_round", 1)
            if server_round != client_round:
                conflict_detected = "CONCURRENT_OFFICER_EDIT"
                conflict_info = {
                    "reason": f"Application round advanced on server from R{client_round} to R{server_round}.",
                    "client_round": client_round,
                    "server_round": server_round,
                }

        # Scenario 3: Institution Evidence Replacement
        if app and not conflict_detected:
            # Check if any new document was submitted on server after bundle export
            exported_at_str = bundle_metadata.get("exported_at") if bundle_metadata else None
            if exported_at_str:
                try:
                    exp_dt = datetime.fromisoformat(exported_at_str)
                    newer_docs = list(db.scalars(
                        select(Document).where(
                            Document.application_id == app.id,
                            Document.created_at > exp_dt,
                        )
                    ).all())
                    if newer_docs:
                        conflict_detected = "INSTITUTION_EVIDENCE_REPLACED"
                        conflict_info = {
                            "reason": f"Institution uploaded {len(newer_docs)} replacement document(s) on server while officer was offline.",
                            "new_documents": [d.original_filename for d in newer_docs],
                        }
                except Exception:
                    pass

        status = "SYNCHRONIZED"
        if conflict_detected:
            status = "CONFLICT_DETECTED"
            conflicts.append({
                "event_id": event_id,
                "conflict_type": conflict_detected,
                "conflict_details": conflict_info,
            })

        sync_rec = OfflineSyncEvent(
            event_id=event_id,
            inspection_id=insp_id,
            application_id=app_id,
            officer_id=officer_id,
            event_type=event_type,
            payload=payload,
            status=status,
            conflict_type=conflict_detected,
            conflict_details=conflict_info if conflict_detected else None,
            receipt_id=receipt_id,
            synced_at=datetime.now(UTC) if status == "SYNCHRONIZED" else None,
        )
        db.add(sync_rec)

        # If clean, apply state modifications
        if status == "SYNCHRONIZED":
            _apply_clean_event(db, inspection, app, event_type, payload, officer_id)

        processed_events.append({
            "event_id": event_id,
            "status": status,
            "conflict_type": conflict_detected,
            "receipt_id": receipt_id,
        })

    db.commit()

    # Record into append-only Merkle audit ledger
    record(
        db,
        actor=officer_id,
        actor_role="officer",
        action="inspection.offline_sync_processed",
        object_type="sync_batch",
        object_id=receipt_id,
        details={
            "receipt_id": receipt_id,
            "total_events": len(events),
            "processed_count": len(processed_events),
            "conflicts_count": len(conflicts),
        },
    )
    db.commit()

    receipt = generate_sync_receipt(
        db,
        receipt_id=receipt_id,
        officer_id=officer_id,
        processed_count=len(processed_events) - len(conflicts),
        conflicts_count=len(conflicts),
    )

    return {
        "receipt": receipt,
        "processed_events": processed_events,
        "conflicts": conflicts,
        "conflicts_count": len(conflicts),
        "status": "requires_officer_review" if conflicts else "synchronized_cleanly",
    }


def _apply_clean_event(
    db: Session,
    inspection: FieldInspectionCase | None,
    app: Application | None,
    event_type: str,
    payload: dict[str, Any],
    officer_id: str,
) -> None:
    """Applies a verified, non-conflicted event to the database."""
    if event_type == "inspection_created":
        # Create inspection case if not present
        case_no = payload.get("case_number")
        if case_no and not inspection:
            insp = FieldInspectionCase(
                case_number=case_no,
                application_id=payload.get("application_id"),
                institution_id=payload.get("institution_id"),
                assigned_officer_id=officer_id,
                status=payload.get("status", "draft"),
                scheduled_date=payload.get("scheduled_date"),
                checklist=payload.get("checklist", []),
                observations=payload.get("observations", []),
                summary=payload.get("summary"),
            )
            db.add(insp)

    elif event_type == "checklist_updated" and inspection:
        inspection.checklist = payload.get("checklist", inspection.checklist)
        inspection.status = "in_progress"

    elif event_type == "observations_added" and inspection:
        obs = list(inspection.observations or [])
        obs.extend(payload.get("observations", []))
        inspection.observations = obs

    elif event_type == "report_signed" and inspection:
        inspection.report_digest = payload.get("report_digest")
        inspection.signature = payload.get("signature")
        inspection.signer_kid = payload.get("signer_kid")
        inspection.signed_payload = payload.get("signed_payload")
        inspection.status = "signed"
        inspection.signed_at = datetime.now(UTC)


def resolve_sync_conflict(
    db: Session,
    event_id: str,
    officer_id: str,
    decision: str,  # "RESOLVED" (accept field edit) or "REJECTED" (keep server version)
    resolution_notes: str,
) -> dict[str, Any]:
    """Applies an official officer determination to a flagged synchronization conflict."""
    evt = db.scalars(
        select(OfflineSyncEvent).where(OfflineSyncEvent.event_id == event_id)
    ).first()

    if not evt:
        raise ValueError(f"Sync event {event_id} not found")

    if evt.status not in ("CONFLICT_DETECTED", "REQUIRES_OFFICER_REVIEW"):
        raise ValueError(f"Event {event_id} is in status '{evt.status}', not in conflict")

    resolution_info = {
        "resolved_by": officer_id,
        "resolved_at": datetime.now(UTC).isoformat(),
        "decision": decision,
        "notes": resolution_notes,
    }

    evt.resolution = resolution_info
    evt.status = decision
    evt.synced_at = datetime.now(UTC)

    # If accepted, apply payload
    if decision == "RESOLVED":
        inspection = db.get(FieldInspectionCase, evt.inspection_id) if evt.inspection_id else None
        app = db.get(Application, evt.application_id) if evt.application_id else None
        _apply_clean_event(db, inspection, app, evt.event_type, evt.payload, officer_id)

    record(
        db,
        actor=officer_id,
        actor_role="officer",
        action="inspection.conflict_resolved",
        object_type="sync_event",
        object_id=event_id,
        details={
            "event_id": event_id,
            "decision": decision,
            "resolution_notes": resolution_notes,
        },
    )
    db.commit()

    return {
        "event_id": event_id,
        "status": decision,
        "resolution": resolution_info,
        "resolved_at": resolution_info["resolved_at"],
    }
