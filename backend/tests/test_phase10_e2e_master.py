"""Phase 10: Master End-to-End System Validation Suite for SIH 2026.

Integrates:
1. Enterprise Institution Onboarding
2. Cross-Document Consistency Intelligence
3. Multi-Dimensional Explainable Risk Scoring
4. Purpose-Bound Consent & 12-Step Government Verification
5. Regulatory RAG Statutory Retrieval
6. Officer Digital Signing & SHA-256 Merkle Audit Checkpoint
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from pramana.audit import record, verify_chain
from pramana.auth import hash_password
from pramana.db import SessionLocal, init_db
from pramana.integrations.consent import default_consent_service
from pramana.integrations.registry import default_registry
from pramana.integrations.verification import default_verification_engine
from pramana.intelligence.cross_document import default_cross_document_engine
from pramana.intelligence.explainable_risk import default_risk_engine
from pramana.intelligence.regulatory_rag import default_rag_engine
from pramana.main import app
from pramana.models import Institution, User


@pytest.fixture(autouse=True)
def setup_master_env():
    init_db()
    with SessionLocal() as db:
        default_registry.initialize_default_providers(db)
        # Ensure admin exists
        admin = db.scalars(select(User).where(User.username == "admin")).first()
        if not admin:
            db.add(User(
                username="admin",
                role="admin",
                password_hash=hash_password("Pramana@2026"),
                active=True,
                display_name="Super Admin",
            ))
            db.commit()
    yield


def test_complete_sih_master_journey():
    client = TestClient(app)

    # Step 1: Admin logs in
    login_res = client.post("/api/auth/login", json={"username": "admin", "password": "Pramana@2026"})
    assert login_res.status_code == 200
    csrf_token = login_res.json()["csrf_token"]
    client.headers["x-csrf-token"] = csrf_token

    # Step 2: Enterprise Onboarding of Demonstration Institution
    inst_payload = {
        "name": "SIH National Institute of Robotics & AI",
        "aicte_id": "1-SIH-2026-DEMO",
        "state": "Maharashtra",
        "category": "Engineering & Technology",
        "contact_email": "dean@sih-robotics.edu.in",
        "admin_username": "sih_dean_2026",
        "admin_password": "SihDeanPassword@2026",
    }
    onboard_res = client.post("/api/admin/institutions/onboard", json=inst_payload)
    assert onboard_res.status_code == 200
    assert onboard_res.json()["status"] == "ONBOARDED"
    inst_id = onboard_res.json()["institution_id"]

    # Step 3: Run Cross-Document Intelligence on Submitted Evidence
    app_meta = {
        "institution_name": "SIH National Institute of Robotics & AI",
        "society_name": "SIH Educational Trust",
        "survey_number": "SN-2026/SIH-A",
        "land_area_acres": 5.0,
    }
    extracted_docs = [
        {
            "doc_id": "DOC-LAND-SIH",
            "doc_type": "LAND_AFFIDAVIT",
            "extracted_facts": {"survey_number": "SN-2026/SIH-A"},
        },
        {
            "doc_id": "DOC-SOC-SIH",
            "doc_type": "SOCIETY_REGISTRATION",
            "extracted_facts": {"society_name": "SIH Educational Trust"},
        },
    ]
    xdoc_findings = default_cross_document_engine.analyze_application_documents(app_meta, extracted_docs)
    # Both documents match application metadata cleanly
    assert len(xdoc_findings) == 0

    # Step 4: Run Explainable Risk Assessment
    risk_report = default_risk_engine.assess_application_risk(
        application_id="APP-SIH-2026-001",
        document_authenticity_findings=[],
        compliance_findings=[],
        cross_document_findings=xdoc_findings,
    )
    assert risk_report.overall_risk_score <= 25.0
    assert risk_report.risk_category == "LOW"
    assert "Decision support only" in risk_report.disclaimer or "decision-support" in risk_report.disclaimer.lower()

    # Step 5: Grant Consent and Execute 12-Step Government Verification
    with SessionLocal() as db:
        consent = default_consent_service.grant_consent(
            db=db,
            application_id="APP-SIH-2026-001",
            institution_id=inst_id,
            provider_id="apisetu_national",
            document_category="LAND_REGISTRY",
            purpose="SIH 2026 Final Demonstration - Land Verification",
            validity_days=30,
            operator="sih_dean_2026",
        )
        assert consent.status == "ACTIVE"

        verify_res = default_verification_engine.verify_document_against_government(
            db=db,
            application_id="APP-SIH-2026-001",
            document_id="DOC-LAND-SIH",
            provider_id="apisetu_national",
            document_category="LAND_REGISTRY",
            document_bytes=b"%PDF-1.4 Simulated Clean Affidavit Evidence",
            query_params={"survey_number": "SN-2026/SIH-A", "state": "Maharashtra", "district": "Pune"},
            initiated_by="scrutiny_officer_lead",
        )
        assert verify_res["verdict"] == "VERIFIED_BY_AUTHORIZED_ISSUER"
        assert len(verify_res["steps_executed"]) == 12

    # Step 6: Query Regulatory RAG with Grounded Citations
    rag_res = default_rag_engine.query_regulations("land requirements for engineering college")
    assert rag_res.status in ("ANSWERED", "INSUFFICIENT_REGULATORY_EVIDENCE")
    if rag_res.status == "ANSWERED":
        assert len(rag_res.citations) >= 1
        assert rag_res.citations[0].verified is True

    # Step 7: Verify Hash-Chained Audit Ledger
    with SessionLocal() as db:
        audit_check = verify_chain(db)
        assert audit_check["intact"] is True
        assert audit_check["events_checked"] > 0
