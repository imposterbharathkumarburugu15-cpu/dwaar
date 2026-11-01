"""Demonstration data seeder for PRAMANA Offline Field Scrutiny.

Creates representative on-site inspection cases, structured checklists, observations,
and revocation snapshots for demonstration institutions.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Application, Institution, User
from .evidence import record_field_evidence
from .models import FieldInspectionCase, InspectionEvidence, OfflineRevocationCache
from .signing import default_keystore


def seed_offline_field_cases(db: Session, officer_user: User) -> None:
    """Seeds realistic field inspection cases and revocation records."""
    # Check if already seeded
    existing = db.scalars(select(FieldInspectionCase)).first()
    if existing:
        return

    # Find APP-2026-000107 (Panchganga) and APP-2026-000101 (Sahyadri)
    app107 = db.get(Application, "APP-2026-000107")
    app101 = db.get(Application, "APP-2026-000101")
    app111 = db.get(Application, "APP-2026-000111")

    now = datetime.now(UTC)

    # 1. Inspection Case 1: Panchganga Institute of Technology (In Progress)
    if app107:
        insp1 = FieldInspectionCase(
            case_number="INSP-2026-000107-01",
            application_id=app107.id,
            institution_id=app107.institution_id,
            assigned_officer_id=officer_user.id,
            status="in_progress",
            scheduled_date=(now - timedelta(days=1)).strftime("%Y-%m-%d"),
            started_at=now - timedelta(hours=5),
            checklist=[
                {
                    "item_id": "CHK-LAND",
                    "title": "Physical Land Boundary Verification",
                    "declared_value": "4.5 Acres (Continuous contiguous plot)",
                    "observed_value": "4.2 Acres surveyed on ground. Northern boundary shared with agricultural canal.",
                    "status": "partial",
                    "notes": "Survey marker stone 4 is offset by 12 meters from revenue sketch.",
                },
                {
                    "item_id": "CHK-BUILDING",
                    "title": "Built-up Area & Floor Plan Inspection",
                    "declared_value": "8,500 Sq.m across 3 academic blocks",
                    "observed_value": "8,420 Sq.m verified. Block C top floor under construction.",
                    "status": "verified",
                    "notes": "Occupancy certificate verified for Blocks A & B.",
                },
                {
                    "item_id": "CHK-LABS",
                    "title": "Computer Lab Workstation Count",
                    "declared_value": "60 Core-i7 Terminals with Gigabit LAN",
                    "observed_value": "58 operational terminals, 2 in repair bay.",
                    "status": "verified",
                    "notes": "Licensed CAD software installed and verified on 30 systems.",
                },
                {
                    "item_id": "CHK-FIRE",
                    "title": "Fire Hydrant & Safety Extinguisher Audit",
                    "declared_value": "Valid Fire NOC Certified; 12 Type-ABC Cylinders",
                    "observed_value": "12 Cylinders inspected. Pressure gauges in green zone.",
                    "status": "verified",
                    "notes": "Next hydrostatic pressure test due in August 2027.",
                },
                {
                    "item_id": "CHK-INTERNET",
                    "title": "Bandwidth Speedtest & Service Provider Router",
                    "declared_value": "300 Mbps Dedicated Leased Line (1:1 contention)",
                    "observed_value": "285 Mbps symmetrical throughput measured at server rack.",
                    "status": "verified",
                    "notes": "BSNL FTTH optical termination unit serial verified.",
                },
                {
                    "item_id": "CHK-FACULTY",
                    "title": "Faculty Physical Attendance & Biometric Register",
                    "declared_value": "24 Full-Time Cadre Faculty",
                    "observed_value": "21 present on campus, 2 on approved conference leave, 1 on medical leave.",
                    "status": "verified",
                    "notes": "Aadhaar-enabled attendance system logs inspected for past 90 days.",
                },
            ],
            observations=[
                {
                    "timestamp": (now - timedelta(hours=4)).isoformat(),
                    "recorded_by": officer_user.username,
                    "content": "Commenced physical scrutiny of administrative block and computer center.",
                    "location_geo": {"latitude": 18.5204, "longitude": 73.8567, "accuracy_meters": 8.5},
                },
                {
                    "timestamp": (now - timedelta(hours=2)).isoformat(),
                    "recorded_by": officer_user.username,
                    "content": "Photographed computer lab terminals and server rack switches.",
                    "location_geo": {"latitude": 18.5205, "longitude": 73.8568, "accuracy_meters": 6.2},
                },
            ],
            summary="Physical inspection indicates overall compliance with APH 2024-27 standards. Minor land demarcation rectification requested for northern survey stone.",
            recommendation="rectify",
        )
        db.add(insp1)
        db.flush()

        # Add sample evidence
        record_field_evidence(
            db=db,
            inspection_id=insp1.id,
            institution_id=app107.institution_id,
            officer_id=officer_user.username,
            category="image",
            file_reference="lab_workstations_inspection.jpg",
            file_bytes=b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xFF\xDB\x00C\x00Inspection Lab Workstation Photo 60 Terminals Active",
            mime_type="image/jpeg",
            description="On-site photograph of central computing laboratory showing active terminal cluster.",
            location_geo={"latitude": 18.5205, "longitude": 73.8568, "accuracy_meters": 5.0},
            device_metadata={"device_model": "Regulatory Scrutiny Tablet Tab-S9", "os": "Android 15 Secured"},
        )

    # 2. Inspection Case 2: Sahyadri College (Signed & Completed)
    if app101:
        insp2 = FieldInspectionCase(
            case_number="INSP-2026-000101-01",
            application_id=app101.id,
            institution_id=app101.institution_id,
            assigned_officer_id=officer_user.id,
            status="signed",
            scheduled_date=(now - timedelta(days=3)).strftime("%Y-%m-%d"),
            started_at=now - timedelta(days=3, hours=4),
            completed_at=now - timedelta(days=3, hours=1),
            checklist=[
                {"item_id": "CHK-LAND", "title": "Physical Land Boundary Verification", "declared_value": "5.0 Acres", "observed_value": "5.0 Acres verified", "status": "verified", "notes": "Fenced perimeter intact."},
                {"item_id": "CHK-BUILDING", "title": "Built-up Area & Floor Plan Inspection", "declared_value": "10,200 Sq.m", "observed_value": "10,200 Sq.m verified", "status": "verified", "notes": "All safety staircases clear."},
                {"item_id": "CHK-LABS", "title": "Computer Lab Workstation Count", "declared_value": "90 Terminals", "observed_value": "90 Terminals operational", "status": "verified", "notes": "UPS backup verified."},
                {"item_id": "CHK-FIRE", "title": "Fire Hydrant & Safety Extinguisher Audit", "declared_value": "Fire NOC Valid", "observed_value": "NOC displayed at entrance", "status": "verified", "notes": "No deficiency."},
                {"item_id": "CHK-INTERNET", "title": "Bandwidth Speedtest", "declared_value": "500 Mbps", "observed_value": "492 Mbps measured", "status": "verified", "notes": "Optical fiber redundancy present."},
                {"item_id": "CHK-FACULTY", "title": "Faculty Physical Attendance", "declared_value": "32 Cadre", "observed_value": "32 Cadre physically verified", "status": "verified", "notes": "Biometrics verified."},
            ],
            observations=[
                {"timestamp": (now - timedelta(days=3, hours=3)).isoformat(), "recorded_by": officer_user.username, "content": "Full on-site verification completed cleanly."}
            ],
            summary="Complete compliance confirmed across all 6 physical dimensions. All land titles, fire safety systems, and faculty registers match regulatory disclosures.",
            recommendation="approve",
        )
        db.add(insp2)
        db.flush()

        # Sign report digitally with Ed25519
        report_payload = {
            "case_number": insp2.case_number,
            "application_id": insp2.application_id,
            "institution_id": insp2.institution_id,
            "officer_id": officer_user.username,
            "checklist": insp2.checklist,
            "observations": insp2.observations,
            "summary": insp2.summary,
            "recommendation": insp2.recommendation,
            "evidence_hashes": [],
            "total_evidence_count": 0,
        }
        signed_info = default_keystore.sign_report(report_payload, officer_id=officer_user.username)
        insp2.report_digest = signed_info["report_digest"]
        insp2.signature = signed_info["signature"]
        insp2.signer_kid = signed_info["signer_kid"]
        insp2.signed_at = datetime.fromisoformat(signed_info["signed_at"])
        insp2.signed_payload = report_payload

    # 3. Seed sample revocation cache entries for offline QR testing
    db.add(OfflineRevocationCache(
        token_jti="JTI-REVOKED-2026-FIRE-NOC",
        revoked=True,
        revocation_reason="Municipal Fire Authority suspended license due to pressure valve failure (Notice #MFA/2026/88)",
        revoked_at=now - timedelta(days=5),
        last_sync_timestamp=now,
    ))
    db.add(OfflineRevocationCache(
        token_jti="JTI-REVOKED-2026-SURVEY-AFFIDAVIT",
        revoked=True,
        revocation_reason="Sub-registrar cancelled registration following civil title dispute (Decree #CS/2026/104)",
        revoked_at=now - timedelta(days=12),
        last_sync_timestamp=now,
    ))

    db.commit()

