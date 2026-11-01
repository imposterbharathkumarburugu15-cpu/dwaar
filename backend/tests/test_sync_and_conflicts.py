"""Tests for Secure Synchronization and Conflict Resolution Engine (Modules 5, 6, 7).

Verifies:
1. Idempotent synchronization event ingestion.
2. Duplicate event re-transmission handling.
3. CONCURRENT_OFFICER_EDIT conflict detection when server round advances.
4. SIGNED_REPORT_EVIDENCE_ALTERED conflict detection when trying to modify signed reports.
5. Official conflict resolution workflow with auditable officer decisions.
6. Verifiable sync receipt generation bound to Merkle audit head.
"""

from datetime import UTC, datetime, timedelta
import uuid
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pramana import audit
from pramana.db import Base
from pramana.models import Application, AuditEvent, Institution, User
from pramana.offline.models import FieldInspectionCase, OfflineSyncEvent
from pramana.offline.sync_engine import (
    generate_sync_receipt,
    process_offline_event_batch,
    resolve_sync_conflict,
)


@pytest.fixture
def memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        # Seed test institution and application
        inst = Institution(id="INST-0001", aicte_id="1-0001", name="Test College of Technology")
        session.add(inst)
        app = Application(
            id="APP-2026-000101",
            institution_id="INST-0001",
            category="Engineering",
            academic_year="2026-27",
            status="under_scrutiny",
            round=1,
            declared={"land_area_acres": 5.0},
        )
        session.add(app)
        user = User(id="usr-officer", username="officer_deshmukh", role="officer", display_name="Officer Deshmukh", password_hash="hash")
        session.add(user)
        session.commit()
        yield session


def test_idempotent_event_batch_synchronization(memory_db):
    """Test 1: Offline event batch is processed cleanly and produces a verifiable sync receipt."""
    events = [
        {
            "event_id": "evt-001-create-insp",
            "event_type": "inspection_created",
            "application_id": "APP-2026-000101",
            "payload": {
                "case_number": "INSP-2026-000101-01",
                "application_id": "APP-2026-000101",
                "institution_id": "INST-0001",
                "status": "in_progress",
                "checklist": [{"item_id": "CHK-LAND", "status": "verified"}],
            },
        }
    ]

    res = process_offline_event_batch(
        db=memory_db,
        officer_id="officer_deshmukh",
        events=events,
    )

    assert res["status"] == "synchronized_cleanly"
    assert res["conflicts_count"] == 0
    assert len(res["processed_events"]) == 1
    assert res["processed_events"][0]["status"] == "SYNCHRONIZED"

    # Verify receipt
    receipt = res["receipt"]
    assert receipt["receipt_id"].startswith("RCPT-")
    assert receipt["events_processed"] == 1
    assert "merkle_head_hash" in receipt

    # Verify inspection was created in database
    insp = memory_db.query(FieldInspectionCase).filter_by(case_number="INSP-2026-000101-01").first()
    assert insp is not None
    assert insp.status == "in_progress"


def test_duplicate_event_handling_idempotency(memory_db):
    """Test 2: Re-transmitting the same event ID returns DUPLICATE_IGNORED and doesn't duplicate records."""
    event_id = "evt-idempotent-002"
    events = [
        {
            "event_id": event_id,
            "event_type": "inspection_created",
            "application_id": "APP-2026-000101",
            "payload": {
                "case_number": "INSP-2026-000101-02",
                "application_id": "APP-2026-000101",
                "institution_id": "INST-0001",
                "status": "in_progress",
            },
        }
    ]

    # First sync
    res1 = process_offline_event_batch(db=memory_db, officer_id="officer_deshmukh", events=events)
    assert res1["processed_events"][0]["status"] == "SYNCHRONIZED"

    # Second sync of identical event
    res2 = process_offline_event_batch(db=memory_db, officer_id="officer_deshmukh", events=events)
    assert res2["processed_events"][0]["status"] == "DUPLICATE_IGNORED"

    # Confirm only one case was created in database
    count = memory_db.query(FieldInspectionCase).filter_by(case_number="INSP-2026-000101-02").count()
    assert count == 1


def test_concurrent_round_conflict_detection(memory_db):
    """Test 3: Detects CONCURRENT_OFFICER_EDIT when server round advanced while offline."""
    app = memory_db.get(Application, "APP-2026-000101")
    app.round = 2  # Server has advanced to Round 2
    memory_db.commit()

    events = [
        {
            "event_id": "evt-conflict-round",
            "event_type": "observations_added",
            "application_id": "APP-2026-000101",
            "payload": {"observations": [{"content": "Verified on Round 1 documents"}]},
        }
    ]

    # Bundle metadata says client was inspecting Round 1
    bundle_meta = {
        "application_id": "APP-2026-000101",
        "application_round": 1,
        "exported_at": datetime.now(UTC).isoformat(),
    }

    res = process_offline_event_batch(
        db=memory_db,
        officer_id="officer_deshmukh",
        events=events,
        bundle_metadata=bundle_meta,
    )

    assert res["status"] == "requires_officer_review"
    assert res["conflicts_count"] == 1
    conflict = res["conflicts"][0]
    assert conflict["conflict_type"] == "CONCURRENT_OFFICER_EDIT"
    assert conflict["conflict_details"]["server_round"] == 2
    assert conflict["conflict_details"]["client_round"] == 1


def test_signed_report_evidence_alteration_conflict(memory_db):
    """Test 4: Detects SIGNED_REPORT_EVIDENCE_ALTERED when trying to modify signed reports."""
    # Create already-signed inspection case
    insp = FieldInspectionCase(
        id="ins-signed-01",
        case_number="INSP-SIGNED-001",
        application_id="APP-2026-000101",
        institution_id="INST-0001",
        assigned_officer_id="usr-officer",
        status="signed",
        signed_at=datetime.now(UTC),
        signature="dummy-signature",
    )
    memory_db.add(insp)
    memory_db.commit()

    events = [
        {
            "event_id": "evt-alter-signed-report",
            "event_type": "checklist_updated",
            "inspection_id": "ins-signed-01",
            "application_id": "APP-2026-000101",
            "payload": {"checklist": [{"item_id": "CHK-LAND", "status": "failed"}]},
        }
    ]

    res = process_offline_event_batch(
        db=memory_db,
        officer_id="officer_deshmukh",
        events=events,
    )

    assert res["conflicts_count"] == 1
    conflict = res["conflicts"][0]
    assert conflict["conflict_type"] == "SIGNED_REPORT_EVIDENCE_ALTERED"


def test_official_conflict_resolution_workflow(memory_db):
    """Test 5: Officer reviews conflict and officially records determination with audit log."""
    # Create an event in conflict
    sync_evt = OfflineSyncEvent(
        event_id="evt-flagged-conflict",
        application_id="APP-2026-000101",
        officer_id="officer_deshmukh",
        event_type="checklist_updated",
        payload={"checklist": [{"item_id": "CHK-LAND", "status": "verified"}]},
        status="CONFLICT_DETECTED",
        conflict_type="CONCURRENT_OFFICER_EDIT",
    )
    memory_db.add(sync_evt)
    memory_db.commit()

    # Officer resolves conflict by approving
    res = resolve_sync_conflict(
        db=memory_db,
        event_id="evt-flagged-conflict",
        officer_id="officer_deshmukh",
        decision="RESOLVED",
        resolution_notes="Officer verified on-site land survey supersedes outdated registry entry.",
    )

    assert res["status"] == "RESOLVED"
    assert res["resolution"]["decision"] == "RESOLVED"
    assert "supersedes" in res["resolution"]["notes"]

    # Verify audit event was appended
    from sqlalchemy import select
    audit_evt = memory_db.scalars(
        select(AuditEvent).where(AuditEvent.action == "inspection.conflict_resolved")
    ).first()
    assert audit_evt is not None
    assert audit_evt.object_id == "evt-flagged-conflict"
