"""Tests for 12-Step Government Document Verification Pipeline."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pramana.db import Base
from pramana.integrations.consent import default_consent_service
from pramana.integrations.models import ExternalVerificationRequest, ExternalVerificationResult
from pramana.integrations.registry import default_registry
from pramana.integrations.verification import GovernmentDocumentVerificationEngine, VERIFICATION_STEPS


@pytest.fixture
def db_session(tmp_path):
    db_file = tmp_path / "test_gov_verify.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        default_registry.initialize_default_providers(session)
        yield session
    engine.dispose()


def test_12_step_verification_success(db_session):
    engine = GovernmentDocumentVerificationEngine()

    # Pre-grant consent
    default_consent_service.grant_consent(
        db=db_session,
        application_id="APP-VER-01",
        institution_id="INST-01",
        provider_id="apisetu_national",
        document_category="LAND_REGISTRY",
        purpose="AICTE Affiliation Verification",
        validity_days=30,
    )

    doc_bytes = b"%PDF-1.4 Simulated Clean Affidavit Evidence"
    res = engine.verify_document_against_government(
        db=db_session,
        application_id="APP-VER-01",
        document_id="DOC-LAND-01",
        provider_id="apisetu_national",
        document_category="LAND_REGISTRY",
        document_bytes=doc_bytes,
        query_params={"survey_number": "SN-402/A", "state": "Maharashtra", "district": "Pune"},
        initiated_by="officer_lead",
    )

    assert res["status"] == "COMPLETED"
    assert res["verdict"] == "VERIFIED_BY_AUTHORIZED_ISSUER"
    assert len(res["steps_executed"]) == 12
    assert res["steps_executed"] == VERIFICATION_STEPS
    assert res["is_simulation"] is True

    # Check database persistence
    db_req = db_session.get(ExternalVerificationRequest, res["verification_id"])
    assert db_req is not None
    assert db_req.status == "COMPLETED"
    assert len(db_req.results) == 1
    assert db_req.results[0].verdict == "VERIFIED_BY_AUTHORIZED_ISSUER"


def test_verification_detects_metadata_mismatch(db_session):
    engine = GovernmentDocumentVerificationEngine()

    default_consent_service.grant_consent(
        db=db_session,
        application_id="APP-VER-02",
        institution_id="INST-02",
        provider_id="apisetu_national",
        document_category="LAND_REGISTRY",
        purpose="Verification",
        validity_days=30,
    )

    res = engine.verify_document_against_government(
        db=db_session,
        application_id="APP-VER-02",
        document_id="DOC-LAND-02",
        provider_id="apisetu_national",
        document_category="LAND_REGISTRY",
        document_bytes=b"%PDF-1.4 Fake Document",
        query_params={
            "survey_number": "SN-402/A",
            "claimed_survey": "SN-FORGED-999",  # Contradicts government survey number
            "state": "Maharashtra",
            "district": "Pune",
        },
    )

    assert res["verdict"] == "DOCUMENT_MISMATCH"
    assert len(res["discrepancies"]) >= 1
    assert res["discrepancies"][0]["field"] == "survey_number"

