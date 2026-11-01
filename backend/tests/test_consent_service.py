"""Tests for Purpose-Bound Consent and Authorization Management."""

from datetime import UTC, datetime, timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pramana.db import Base
from pramana.integrations.consent import ConsentService, ConsentExpiredError, ConsentRevokedError


@pytest.fixture
def db_session(tmp_path):
    db_file = tmp_path / "test_consent.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_grant_and_verify_active_consent(db_session):
    service = ConsentService()
    consent = service.grant_consent(
        db=db_session,
        application_id="APP-2026-0001",
        institution_id="INST-001",
        provider_id="apisetu_national",
        document_category="LAND_REGISTRY",
        purpose="AICTE Approval Scrutiny - Land Verification",
        validity_days=30,
    )
    assert consent.id.startswith("consent_")
    assert consent.status == "ACTIVE"
    assert consent.audit_event_id is not None

    # Verify active
    verified = service.verify_active_consent(
        db=db_session,
        application_id="APP-2026-0001",
        provider_id="apisetu_national",
        document_category="LAND_REGISTRY",
    )
    assert verified.id == consent.id


def test_consent_revocation(db_session):
    service = ConsentService()
    consent = service.grant_consent(
        db=db_session,
        application_id="APP-2026-0002",
        institution_id="INST-002",
        provider_id="digilocker_nad",
        document_category="ACADEMIC_LOA",
        purpose="Verification",
        validity_days=30,
    )

    revoked = service.revoke_consent(
        db=db_session,
        consent_id=consent.id,
        revoked_by="applicant_user",
        reason="Application withdrawn",
    )
    assert revoked.status == "REVOKED"
    assert revoked.revoked_at is not None

    # Querying after revocation fails
    with pytest.raises(KeyError):
        service.verify_active_consent(
            db=db_session,
            application_id="APP-2026-0002",
            provider_id="digilocker_nad",
            document_category="ACADEMIC_LOA",
        )


def test_consent_expiration(db_session):
    service = ConsentService()
    consent = service.grant_consent(
        db=db_session,
        application_id="APP-2026-0003",
        institution_id="INST-003",
        provider_id="apisetu_national",
        document_category="FIRE_NOC",
        purpose="Verification",
        validity_days=-1,  # Expired yesterday
    )

    with pytest.raises(ConsentExpiredError):
        service.verify_active_consent(
            db=db_session,
            application_id="APP-2026-0003",
            provider_id="apisetu_national",
            document_category="FIRE_NOC",
        )

