"""Test Suite for Module 7 & 8: Scoped Trust Store Management & Incident Recovery."""

from datetime import UTC, datetime, timedelta
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from pramana.db import Base
from pramana.models import User
from pramana.trust.certificates import register_certificate
from pramana.trust.incident import execute_incident_recovery, raise_security_incident
from pramana.trust.kms import kms_service
from pramana.trust.models import CryptographicKey, SecurityIncident, TrustStoreEntry
from pramana.trust.trust_store import default_trust_store


@pytest.fixture
def trust_db(tmp_path):
    db_path = tmp_path / "trust_test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        admin = User(
            username="admin",
            role="super_admin",
            display_name="Security Admin",
            password_hash="test",
        )
        session.add(admin)
        session.commit()
        yield session


def _create_sample_cert_pem(common_name: str):
    priv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "AICTE"),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(priv_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(priv_key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")


def test_trust_store_scoping_and_versioning(trust_db):
    pem1 = _create_sample_cert_pem("AICTE Root CA Dev")
    pem2 = _create_sample_cert_pem("AICTE Root CA Prod")

    cert1 = register_certificate(trust_db, pem1)
    cert2 = register_certificate(trust_db, pem2)

    # Add cert1 to development -> version 1
    entry_dev = default_trust_store.add_trust_anchor(
        trust_db, cert1.id, environment="development", operator_username="admin"
    )
    assert entry_dev.trust_store_version == 1
    assert entry_dev.environment == "development"

    # Add cert2 to production -> version 1 for prod
    entry_prod = default_trust_store.add_trust_anchor(
        trust_db, cert2.id, environment="production", operator_username="admin"
    )
    assert entry_prod.trust_store_version == 1
    assert entry_prod.environment == "production"

    # Query scoped anchors
    dev_anchors = default_trust_store.list_trust_anchors(trust_db, environment="development")
    prod_anchors = default_trust_store.list_trust_anchors(trust_db, environment="production")

    assert len(dev_anchors) == 1
    assert dev_anchors[0]["certificate_id"] == cert1.id
    assert len(prod_anchors) == 1
    assert prod_anchors[0]["certificate_id"] == cert2.id

    # Remove dev anchor
    removed = default_trust_store.remove_trust_anchor(
        trust_db, cert1.id, environment="development", operator_username="admin"
    )
    assert removed is True
    assert len(default_trust_store.list_trust_anchors(trust_db, environment="development")) == 0


def test_key_compromise_and_incident_raising(trust_db):
    # 1. Create active key
    key_entry = kms_service.generate_key(
        trust_db,
        key_id="prm-test-compromise-v1",
        algorithm="ED25519",
        key_purpose="audit_signing",
        operator_username="admin",
    )
    assert key_entry.status == "ACTIVE"

    # 2. Raise security incident affecting this key
    incident = raise_security_incident(
        trust_db,
        incident_type="KEY_COMPROMISE",
        description="Private key exposed in public pastebin report",
        reported_by="security_officer",
        affected_key_id="prm-test-compromise-v1",
        severity="CRITICAL",
    )

    assert incident.id is not None
    assert incident.status == "OPEN"
    assert incident.affected_key_id == "prm-test-compromise-v1"

    # Verify key status transitioned immediately to COMPROMISED
    trust_db.refresh(key_entry)
    assert key_entry.status == "COMPROMISED"

    # 3. Attempting to sign with compromised key fails immediately
    with pytest.raises(PermissionError, match="COMPROMISED"):
        kms_service.sign_with_key(trust_db, "prm-test-compromise-v1", b"payload")


def test_execute_incident_recovery_and_replacement_key(trust_db):
    # 1. Create key and mark compromised via incident
    key_entry = kms_service.generate_key(
        trust_db,
        key_id="prm-incident-qr-v1",
        algorithm="ED25519",
        key_purpose="qr_issuance",
        operator_username="admin",
    )
    incident = raise_security_incident(
        trust_db,
        incident_type="SUSPECTED_UNAUTHORIZED_ACCESS",
        description="Irregular access detected on signing worker node",
        reported_by="admin",
        affected_key_id="prm-incident-qr-v1",
    )

    # 2. Execute recovery workflow
    recovery_res = execute_incident_recovery(
        trust_db,
        incident_id=incident.id,
        operator_username="admin",
        generate_replacement_key=True,
        resolution_notes="Node re-imaged, rotated to emergency replacement key v2",
    )

    assert recovery_res["status"] == "RESOLVED"
    replacement_id = recovery_res["replacement_key_id"]
    assert replacement_id is not None
    assert "prm-incident-qr" in replacement_id

    # Verify incident record in DB is RESOLVED
    trust_db.refresh(incident)
    assert incident.status == "RESOLVED"
    assert incident.resolved_at is not None

    # Verify the replacement key is ACTIVE and functional
    rep_key = trust_db.scalars(select(CryptographicKey).where(CryptographicKey.key_id == replacement_id)).first()
    assert rep_key.status == "ACTIVE"
    sig = kms_service.sign_with_key(trust_db, replacement_id, b"new payload")
    assert len(sig) > 0
