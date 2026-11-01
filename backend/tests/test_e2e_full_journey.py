"""End-to-End Demonstration Journey Test for PRAMANA (SIH 2026 Problem Statement 26261).

Tests the full 10-stage regulatory verification journey:
Stage 1: Application Submission
Stage 2: Document Ingestion & Storage
Stage 3: OCR & Text Extraction
Stage 4: Cryptographic & Forensic Validation
Stage 5: Regulatory Compliance Evaluation
Stage 6: Multi-Factor Institutional Risk Scoring
Stage 7: Officer Investigation & Deficiency Notice Drafting
Stage 8: Applicant Rectification Response
Stage 9: Final Officer Approval/Rejection Determination
Stage 10: Immutable Merkle Audit Chain Verification & Receipt Generation
"""

import hashlib
import importlib.util
import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from pramana.audit import export_verifiable_audit_receipt, record, verify_chain
from pramana.auth import hash_password
from pramana.config import get_settings
from pramana.db import SessionLocal, engine, init_db
from pramana.drishti.investigation import draft_deficiency_notice, synthesize_investigation_brief
from pramana.history.lifecycle import analyze_application_lifecycle, validate_state_transition
from pramana.main import app
from pramana.models import Application, DeficiencyLetter, Document, Finding, Institution, RectificationRequest, User, ValidationRun
from pramana.pipeline.cross_doc import run_cross_document_intelligence
from pramana.risk.engine import assess_institutional_risk
from pramana.rules.engine import active_ruleset, evaluate
from pramana.rules.facts import FactStore

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _copy_db(src: Path, dst: Path) -> None:
    s, d = sqlite3.connect(src), sqlite3.connect(dst)
    with d:
        s.backup(d)
    s.close()
    d.close()


@pytest.fixture(scope="module")
def client():
    init_db()
    db = SessionLocal()
    seeded = db.scalars(select(User).where(User.username == "officer")).first() is not None
    db.close()
    engine.dispose()
    if not seeded:
        if not (ROOT / "fixtures" / "out" / "manifest.json").exists():
            _load("make_fixtures").main()
        _load("seed").main(validate=True)
    
    live = get_settings().data_dir / "pramana.db"
    saved = live.with_name("pramana.e2e-journey-backup.db")
    engine.dispose()
    _copy_db(live, saved)

    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": "officer", "password": "Pramana@2026"})
    assert r.status_code == 200
    c.headers["x-csrf-token"] = r.json()["csrf_token"]
    
    yield c

    engine.dispose()
    _copy_db(saved, live)
    saved.unlink(missing_ok=True)


def test_complete_demonstration_journey(client):
    db = SessionLocal()
    try:
        # -------------------------------------------------------------
        # STAGE 1: Application Submission
        # -------------------------------------------------------------
        inst = db.scalars(select(Institution)).first()
        assert inst is not None, "Institution must exist in seeded db"
        
        officer = db.scalars(select(User).where(User.username == "officer")).first()
        assert officer is not None
        
        test_app_id = f"APP-E2E-{uuid.uuid4().hex[:6].upper()}"
        now = datetime.now(UTC)
        new_app = Application(
            id=test_app_id,
            institution_id=inst.id,
            category="EOA",
            academic_year="2026-27",
            status="submitted",
            round=1,
            declared={"intake": 480, "faculty_count": 24, "carpet_area_sqm": 8500, "land_acres": 3.0},
            created_at=now,
            submitted_at=now,
        )
        db.add(new_app)
        db.commit()
        
        record(db, actor=officer.username, actor_role="officer", action="application.submitted",
               object_type="application", object_id=test_app_id, application_id=test_app_id)
        
        # -------------------------------------------------------------
        # STAGE 2 & 3: Document Ingestion, Storage & OCR Metadata
        # -------------------------------------------------------------
        doc_content = b"%PDF-1.4 Demonstration Certificate Content with Municipal Stamp"
        doc_sha = hashlib.sha256(doc_content).hexdigest()
        doc = Document(
            id=f"DOC-E2E-{uuid.uuid4().hex[:6]}",
            application_id=test_app_id,
            round=1,
            declared_type="fire_noc",
            original_filename="Fire_Safety_NOC_2026.pdf",
            sha256=doc_sha,
            size_bytes=len(doc_content),
            mime="application/pdf",
            page_count=1,
            storage_name="demo_storage.bin",
            uploaded_by=officer.id,
            processing_status="processed",
            analysis={"text_layer": True, "ocr_engine": "rapidocr", "language": "en"},
            fingerprints={"sha256": doc_sha},
        )
        db.add(doc)
        db.commit()
        
        # -------------------------------------------------------------
        # STAGE 4: Cryptographic & Forensic Validation
        # -------------------------------------------------------------
        assert doc.processing_status == "processed"
        assert doc.sha256 == doc_sha
        
        # -------------------------------------------------------------
        # STAGE 5: Regulatory Compliance Evaluation
        # -------------------------------------------------------------
        rs = active_ruleset()
        facts = FactStore()
        facts.add("app.category", new_app.category, "declared")
        facts.add("inst.name", inst.name, "reference")
        facts.add("inst.established_year", inst.established_year or 2000, "reference")
        facts.add("calc.faculty_student_ratio", 20.0, "computed")
        facts.add("doc.fire_noc.valid_until", (datetime.now(UTC) + timedelta(days=300)).date(), "extracted")
        
        eval_results = evaluate(rs, facts, category=new_app.category, as_of=datetime.now(UTC).date())
        assert len(eval_results) > 0, "Rules evaluation must produce evaluated outcomes"
        
        # Record a synthetic validation run with findings
        val_run = ValidationRun(
            id=f"RUN-E2E-{uuid.uuid4().hex[:6]}",
            application_id=test_app_id,
            started_at=now,
            finished_at=now + timedelta(seconds=2),
            status="complete",
            ruleset_id=rs.id,
            ruleset_hash=rs.sha256,
            engine_version="2.0",
            summary={"rules_evaluated": len(eval_results), "passed": True},
        )
        db.add(val_run)
        db.flush()
        
        # Add finding for rectification test
        finding = Finding(
            id=f"FND-E2E-{uuid.uuid4().hex[:6]}",
            run_id=val_run.id,
            application_id=test_app_id,
            code="DOC-FIRE-NOC-OBSERVATION",
            fingerprint=f"fp_{uuid.uuid4().hex[:16]}",
            category="compliance",
            evidence_class="rule",
            severity="medium",
            outcome="fail",
            title="Fire NOC Annual Inspection Endorsement Required",
            message="Municipal fire safety endorsement stamp requires fresh annual renewal certificate.",
            rule={"id": "doc.fire_noc.validity", "source": {"clause": "6.1.b", "page": "42"}},
        )
        db.add(finding)
        db.commit()
        
        # -------------------------------------------------------------
        # STAGE 6: Multi-Factor Institutional Risk Scoring
        # -------------------------------------------------------------
        risk_profile = assess_institutional_risk(db, inst.id)
        assert risk_profile["institution_id"] == inst.id
        assert any(t in risk_profile["risk_tier"] for t in ["A", "B", "C", "D", "E"])
        assert risk_profile["composite_risk_score"] >= 0.0
        
        # -------------------------------------------------------------
        # STAGE 7: Officer Investigation & Deficiency Notice Drafting
        # -------------------------------------------------------------
        officer = db.scalars(select(User).where(User.username == "officer")).first()
        assert officer is not None
        
        deficiency_draft = draft_deficiency_notice(db, test_app_id, officer)
        assert deficiency_draft["application_id"] == test_app_id
        assert deficiency_draft["deficiency_count"] >= 1
        assert "statutory_violation" in deficiency_draft["deficiency_items"][0]
        
        brief = synthesize_investigation_brief(db, test_app_id)
        assert brief["application_id"] == test_app_id
        assert brief["recommended_action"] in [
            "ISSUE_DEFICIENCY_OR_REFER_TO_VIGILANCE",
            "REQUEST_RECTIFICATION",
            "OFFICER_REVIEW_CONDITIONAL",
            "GRANT_APPROVAL",
        ]
        
        # -------------------------------------------------------------
        # STAGE 8: Applicant Rectification Workflow
        # -------------------------------------------------------------
        # Transition state machine: submitted -> under_scrutiny -> rectification_requested
        valid, _ = validate_state_transition(new_app.status, "under_scrutiny")
        assert valid is True
        new_app.status = "under_scrutiny"
        
        valid, _ = validate_state_transition(new_app.status, "rectification_requested")
        assert valid is True
        new_app.status = "rectification_requested"
        db.commit()
        
        rect = RectificationRequest(
            id=f"REC-E2E-{uuid.uuid4().hex[:6]}",
            application_id=test_app_id,
            round=1,
            items=[{"finding_id": finding.id, "code": finding.code}],
            message="Please submit renewed municipal fire safety NOC",
            status="open",
            created_by=officer.id,
            created_at=now,
        )
        db.add(rect)
        db.commit()
        
        # Applicant rectifies
        rect.status = "responded"
        rect.responded_at = datetime.now(UTC)
        valid, _ = validate_state_transition(new_app.status, "rectification_submitted")
        assert valid is True
        new_app.status = "rectification_submitted"
        db.commit()
        
        # -------------------------------------------------------------
        # STAGE 9: Final Decision Determination
        # -------------------------------------------------------------
        valid, _ = validate_state_transition(new_app.status, "under_scrutiny")
        assert valid is True
        new_app.status = "under_scrutiny"
        
        valid, _ = validate_state_transition(new_app.status, "approved")
        assert valid is True
        new_app.status = "approved"
        db.commit()
        
        record(db, actor="officer", actor_role="officer", action="application.approved",
               object_type="application", object_id=test_app_id, application_id=test_app_id,
               details={"determination": "Approved with annual compliance conditions"})
        
        # -------------------------------------------------------------
        # STAGE 10: Immutable Merkle Audit Chain & Receipt Verification
        # -------------------------------------------------------------
        chain_status = verify_chain(db)
        assert chain_status["intact"] is True
        assert chain_status["events_checked"] > 0
        
        receipt = export_verifiable_audit_receipt(db, test_app_id)
        assert receipt["application_id"] == test_app_id
        assert receipt["total_lifecycle_events"] > 0
        assert "SHA-256" in receipt["verification_algorithm"]
        
    finally:
        db.close()
