"""Test Suite for Module 4: X.509 Certificate Lifecycle Management & Chain Validation."""

from datetime import UTC, datetime, timedelta
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pramana.db import Base
from pramana.models import User
from pramana.trust.certificates import register_certificate, validate_certificate
from pramana.trust.trust_store import default_trust_store


@pytest.fixture
def cert_db(tmp_path):
    db_path = tmp_path / "cert_test.db"
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


def _generate_test_cert(
    common_name: str,
    days_valid: int = 365,
    issuer_name: str | None = None,
    issuer_key: rsa.RSAPrivateKey | None = None,
    is_ca: bool = False,
    start_offset_days: int = 0,
):
    priv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "AICTE"),
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])
    
    if issuer_name and issuer_key:
        issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "AICTE"),
            x509.NameAttribute(NameOID.COMMON_NAME, issuer_name),
        ])
        signing_key = issuer_key
    else:
        issuer = subject
        signing_key = priv_key

    now = datetime.now(UTC) + timedelta(days=start_offset_days)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(priv_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + timedelta(days=days_valid))
    )
    if is_ca:
        builder = builder.add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)

    cert = builder.sign(signing_key, hashes.SHA256())
    pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    return pem, priv_key, cert


def test_register_certificate_and_metadata_extraction(cert_db):
    pem, _, cert = _generate_test_cert("AICTE Demo Service")
    rec = register_certificate(cert_db, pem)

    assert rec.id is not None
    assert rec.serial_number == str(cert.serial_number)
    assert "AICTE Demo Service" in rec.subject_dn
    assert len(rec.fingerprint_sha256) == 64
    assert rec.revocation_status == "GOOD"


def test_validate_trusted_anchor(cert_db):
    pem, _, _ = _generate_test_cert("PRAMANA Root CA", is_ca=True)
    rec = register_certificate(cert_db, pem, trust_status="TRUSTED_ANCHOR")
    default_trust_store.add_trust_anchor(cert_db, rec.id, environment="development", operator_username="admin")

    result = validate_certificate(cert_db, pem, environment="development")
    assert result.valid is True
    assert result.status == "VALID"
    assert result.is_trust_anchor is True
    assert result.is_self_signed is True


def test_reject_untrusted_self_signed_certificate(cert_db):
    pem, _, _ = _generate_test_cert("Rogue Self-Signed CA", is_ca=True)
    register_certificate(cert_db, pem, trust_status="UNTRUSTED")

    result = validate_certificate(cert_db, pem, environment="development")
    assert result.valid is False
    assert result.status == "UNTRUSTED_ISSUER"
    assert "not registered as a trusted anchor" in result.error


def test_validate_expired_certificate(cert_db):
    # Created 400 days ago, valid for 365 days -> expired 35 days ago
    pem, _, _ = _generate_test_cert("Expired Server Cert", days_valid=365, start_offset_days=-400)
    rec = register_certificate(cert_db, pem, trust_status="TRUSTED_ANCHOR")
    default_trust_store.add_trust_anchor(cert_db, rec.id, environment="development", operator_username="admin")

    result = validate_certificate(cert_db, pem, environment="development")
    assert result.valid is False
    assert result.status == "EXPIRED"
    assert "expired" in result.error.lower()


def test_certificate_chain_validation(cert_db):
    # 1. Create Root CA & mark as trusted anchor
    root_pem, root_key, _ = _generate_test_cert("PRAMANA Trust Root CA", is_ca=True)
    root_rec = register_certificate(cert_db, root_pem, trust_status="TRUSTED_ANCHOR")
    default_trust_store.add_trust_anchor(cert_db, root_rec.id, environment="development", operator_username="admin")

    # 2. Issue Leaf Cert signed by Root CA
    leaf_pem, _, _ = _generate_test_cert(
        "PRAMANA Inspection Tablet Cert",
        days_valid=90,
        issuer_name="PRAMANA Trust Root CA",
        issuer_key=root_key,
        is_ca=False,
    )
    register_certificate(cert_db, leaf_pem, trust_status="UNTRUSTED")

    # 3. Validate Leaf Cert
    result = validate_certificate(cert_db, leaf_pem, environment="development")
    assert result.valid is True
    assert result.status == "VALID"
    assert result.is_self_signed is False
    assert result.is_trust_anchor is False


def test_reject_forged_leaf_signature(cert_db):
    root_pem, _, _ = _generate_test_cert("Legitimate Root CA", is_ca=True)
    root_rec = register_certificate(cert_db, root_pem, trust_status="TRUSTED_ANCHOR")
    default_trust_store.add_trust_anchor(cert_db, root_rec.id, environment="development", operator_username="admin")

    # An attacker generates their own rogue key and signs a leaf claiming to be issued by Legitimate Root CA
    rogue_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged_leaf_pem, _, _ = _generate_test_cert(
        "Forged Client Cert",
        days_valid=30,
        issuer_name="Legitimate Root CA",
        issuer_key=rogue_key,
    )

    result = validate_certificate(cert_db, forged_leaf_pem, environment="development")
    assert result.valid is False
    assert result.status == "INVALID_SIGNATURE"
    assert "signature check failed" in result.error.lower()
