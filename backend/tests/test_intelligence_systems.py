"""Comprehensive Tests for PRAMANA Intelligence Systems & Security Infrastructure.

Tests:
1. Regulatory Intelligence 2.0 (version listing, comparison, what-if simulation)
2. Cross-Document Contradiction & Completeness Analysis
3. Institutional Risk Intelligence (deterministic scoring, factors, sector observatory)
4. Temporal Application Lifecycle & Backdating detection
5. Drishti Investigation Assistant (Deficiency notice drafting & case briefing)
6. Offline Evidence Infrastructure (Bundle export, sync conflict detection, reconciliation)
7. Advanced Audit Engine (Full-chain verification, tamper evidence simulation, receipt export)
8. Granular 7-Role RBAC authorization
"""

import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from pramana.audit import export_verifiable_audit_receipt, simulate_audit_tampering, verify_chain
from pramana.auth import PERMISSIONS, ROLES, has_permission
from pramana.db import SessionLocal, engine, init_db
from pramana.drishti.investigation import draft_deficiency_notice, synthesize_investigation_brief
from pramana.history.lifecycle import analyze_application_lifecycle, validate_state_transition
from pramana.models import Application, Institution, User
from pramana.offline.manager import build_offline_bundle, process_offline_sync, reconcile_offline_conflicts
from pramana.pipeline.cross_doc import run_cross_document_intelligence
from pramana.risk.engine import assess_institutional_risk, compute_sector_risk_observatory
from pramana.rules.simulator import run_simulation
from pramana.rules.versioning import compare_rulesets, list_available_rulesets

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def app():
    """Ensure database is initialized and seeded before running intelligence tests."""
    init_db()
    db = SessionLocal()
    seeded = db.scalars(select(User).where(User.username == "officer")).first() is not None
    db.close()
    engine.dispose()
    if not seeded:
        if not (ROOT / "fixtures" / "out" / "manifest.json").exists():
            _load("make_fixtures").main()
        _load("seed").main(validate=True)
    from pramana.main import app as fastapi_app
    return fastapi_app


@pytest.fixture
def client(app):
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": "officer", "password": "Pramana@2026"})
    assert r.status_code == 200
    c.headers["x-csrf-token"] = r.json()["csrf_token"]
    return c


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def test_regulatory_versioning_and_diff(client):
    """Test Regulatory 2.0 ruleset version discovery and comparative diffing."""
    r = client.get("/api/intelligence/regulatory/rulesets")
    assert r.status_code == 200
    rulesets = r.json()
    assert len(rulesets) >= 3
    ids = {rs["id"] for rs in rulesets}
    assert "aicte-aph-2024-27" in ids
    assert "aicte-aph-2025-26" in ids
    assert "aicte-aph-2027-28-draft" in ids

    # Compare two ruleset versions
    diff = client.get("/api/intelligence/regulatory/compare?v1=aicte-aph-2025-26&v2=aicte-aph-2027-28-draft")
    assert diff.status_code == 200
    d = diff.json()
    assert "summary" in d
    assert "norms_diff" in d
    assert d["summary"]["total_rules_v2"] >= 2


def test_what_if_regulatory_simulation(client, db):
    """Test What-If Regulatory Simulation across institutional applications."""
    payload = {
        "target_ruleset_version": "aicte-aph-2024-27",
        "parameter_overrides": {
            "norms": {"faculty_student_ratio": {"UG_ET": 15}},
        },
    }
    r = client.post("/api/intelligence/regulatory/simulate", json=payload)
    assert r.status_code == 200
    sim = r.json()
    assert "summary" in sim
    assert "total_applications_evaluated" in sim["summary"]
    assert len(sim["applications"]) > 0
    app_res = sim["applications"][0]
    assert "baseline_compliance_score" in app_res
    assert "simulated_compliance_score" in app_res
    assert "status_change" in app_res


def test_cross_document_intelligence(client, db):
    """Test Cross-Document Completeness and Contradiction detection on test application."""
    app_record = db.scalars(select(Application)).first()
    assert app_record is not None
    
    r = client.get(f"/api/intelligence/applications/{app_record.id}/cross-doc")
    assert r.status_code == 200
    data = r.json()
    assert "completeness" in data
    assert "completeness_score" in data["completeness"]
    assert "contradictions" in data
    assert isinstance(data["contradictions"], list)


def test_institutional_risk_intelligence(client, db):
    """Test Institutional Risk Engine: factors, scoring, tiering, and sector observatory."""
    inst = db.scalars(select(Institution)).first()
    assert inst is not None

    r = client.get(f"/api/intelligence/risk/institution/{inst.id}")
    assert r.status_code == 200
    risk = r.json()
    assert 0.0 <= risk["composite_risk_score"] <= 100.0
    assert risk["risk_tier"] in ("Tier A", "Tier B", "Tier C", "Tier D", "Tier E")
    assert "factors" in risk
    assert "recommendation" in risk

    # Sector risk observatory
    obs = client.get("/api/intelligence/risk/observatory")
    assert obs.status_code == 200
    s_data = obs.json()
    assert "tier_distribution" in s_data
    assert "total_institutions" in s_data


def test_temporal_application_lifecycle(client, db):
    """Test Temporal Application Lifecycle: state machine transitions and backdating checks."""
    # Test valid and invalid transitions
    ok, msg = validate_state_transition("draft", "submitted")
    assert ok is True
    
    bad, bad_msg = validate_state_transition("draft", "approved")
    assert bad is False
    assert "Illegal state transition" in bad_msg

    app_record = db.scalars(select(Application)).first()
    r = client.get(f"/api/intelligence/applications/{app_record.id}/lifecycle")
    assert r.status_code == 200
    data = r.json()
    assert "timeline" in data
    assert "temporal_anomalies" in data
    assert "replacement_summary" in data


def test_drishti_investigation_brief_and_deficiency_draft(client, db):
    """Test Drishti AI Assistant: grounded deficiency notice drafting and case briefing."""
    app_record = db.scalars(select(Application)).first()
    
    # Briefing
    brief = client.get(f"/api/intelligence/applications/{app_record.id}/investigation-brief")
    assert brief.status_code == 200
    b_data = brief.json()
    assert "executive_summary" in b_data
    assert "recommended_action" in b_data
    assert "risk_level" in b_data

    # Deficiency Notice Draft
    draft = client.post(f"/api/intelligence/applications/{app_record.id}/deficiency-draft")
    assert draft.status_code == 200
    d_data = draft.json()
    assert "deficiency_items" in d_data
    assert "response_deadline" in d_data
    assert "subject" in d_data


def test_offline_evidence_workspace(client, db):
    """Test Offline Bundle export, sync conflict detection, and reconciliation."""
    app_record = db.scalars(select(Application)).first()
    
    # 1. Export Bundle
    r = client.get(f"/api/intelligence/offline/bundle/{app_record.id}")
    assert r.status_code == 200
    bundle = r.json()
    assert "metadata" in bundle
    assert "inspection_checklist" in bundle
    assert "documents" in bundle
    meta = bundle["metadata"]
    assert "bundle_hash" in meta

    # 2. Sync Clean Offline Data
    sync_payload = {
        "bundle_metadata": meta,
        "local_annotations": [
            {
                "target": "CHK-LAND",
                "content": "On-site survey confirmed demarcated 5-acre campus boundary.",
                "location_geo": {"lat": 18.52, "lng": 73.85},
            }
        ],
        "checklist_updates": [
            {"item_id": "CHK-LAND", "status": "verified_on_site"}
        ],
    }
    sync_res = client.post("/api/intelligence/offline/sync", json=sync_payload)
    assert sync_res.status_code == 200
    s_out = sync_res.json()
    assert s_out["sync_status"] == "synchronized_cleanly"

    # 3. Conflict Detection Simulation (Simulate outdated client round)
    stale_meta = dict(meta)
    stale_meta["application_round"] = 99  # Mismatch against server round
    conflict_payload = {
        "bundle_metadata": stale_meta,
        "local_annotations": [],
        "checklist_updates": [],
    }
    conflict_res = client.post("/api/intelligence/offline/sync", json=conflict_payload)
    assert conflict_res.status_code == 200
    c_out = conflict_res.json()
    assert c_out["sync_status"] == "conflict_detected"
    assert len(c_out["conflicts"]) > 0

    # 4. Manual Reconciliation
    reconcile_payload = {
        "application_id": app_record.id,
        "resolutions": [
            {"item_key": "CHK-LAND", "chosen_source": "offline_field_observation", "note": "Physical inspection takes precedence."}
        ],
    }
    rec_res = client.post("/api/intelligence/offline/reconcile", json=reconcile_payload)
    assert rec_res.status_code == 200
    assert rec_res.json()["status"] == "reconciliation_complete"


def test_advanced_audit_chain_and_tamper_evidence(client, db):
    """Test Cryptographic Audit Chain verification and Tamper Detection simulation."""
    # Full-chain verification
    r = client.get("/api/intelligence/audit/verify-chain")
    assert r.status_code == 200
    v = r.json()
    assert v["intact"] is True
    assert v["events_checked"] > 0
    assert v["first_broken_seq"] is None

    # Tamper simulation demonstration
    tamper = client.post("/api/intelligence/audit/simulate-tamper", json={})
    assert tamper.status_code == 200
    t = tamper.json()
    assert t["chain_intact_prior"] is True
    assert t["chain_intact_after_simulation"] is False
    assert len(t["broken_links"]) > 0
    assert t["broken_links"][0]["status"] == "HASH_MISMATCH_DETECTED"

    # Verifiable receipt export
    app_record = db.scalars(select(Application)).first()
    rcpt = client.get(f"/api/intelligence/audit/receipt/{app_record.id}")
    assert rcpt.status_code == 200
    r_data = rcpt.json()
    assert "receipt_id" in r_data
    assert "total_lifecycle_events" in r_data


def test_seven_role_rbac_matrix():
    """Verify the 7-Role Granular RBAC permissions model."""
    assert len(ROLES) >= 7
    expected_roles = {
        "super_admin", "aicte_admin", "regional_officer",
        "institution_admin", "institution_operator", "applicant", "external_verifier"
    }
    assert expected_roles.issubset(set(ROLES.keys()))

    # Check permission logic
    super_admin = User(username="admin_test", role="super_admin")
    assert has_permission(super_admin, "platform:configure") is True
    assert has_permission(super_admin, "rules:simulate") is True

    reg_officer = User(username="officer_test", role="regional_officer")
    assert has_permission(reg_officer, "platform:configure") is False
    assert has_permission(reg_officer, "apps:scrutinize") is True

    operator = User(username="operator_test", role="institution_operator")
    assert has_permission(operator, "apps:scrutinize") is False
    assert has_permission(operator, "apps:create") is True

    verifier = User(username="verifier_test", role="external_verifier")
    assert has_permission(verifier, "forensics:analyze") is True
    assert has_permission(verifier, "apps:create") is False
