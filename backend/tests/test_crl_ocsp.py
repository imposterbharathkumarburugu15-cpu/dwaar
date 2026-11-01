"""Test Suite for Module 5 & 6: Dynamic CRL Synchronization & OCSP Integration."""

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
from pramana.trust.crl_ocsp import check_revocation_against_crl, sync_crl
from pramana.trust.models import CertificateRecord, CRLRecord


@pytest.fixture
def crl_db(tmp_path):
    db_path = tmp_path / "crl_test.db"
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


def _create_ca_and_cert():
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "AICTE"),
        x509.NameAttribute(NameOID.COMMON_NAME, "AICTE Root CA"),
    ])
    now = datetime.now(UTC)
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(1001)
        .not_valid_before(now - timedelta(days=10))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    ca_pem = ca_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")

    # Client cert to be revoked
    client_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    client_name = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
        x509.NameAttribute(NameOID.COMMON_NAME, "Revoked Institute Cert"),
    ])
    client_serial = 2002
    client_cert = (
        x509.CertificateBuilder()
        .subject_name(client_name)
        .issuer_name(ca_name)
        .public_key(client_key.public_key())
        .serial_number(client_serial)
        .not_valid_before(now - timedelta(days=5))
        .not_valid_after(now + timedelta(days=180))
        .sign(ca_key, hashes.SHA256())
    )
    client_pem = client_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")

    return ca_pem, ca_key, ca_name, client_pem, client_serial


def _build_crl(ca_key, ca_name, crl_number, revoked_serials=None, expired=False):
    now = datetime.now(UTC)
    builder = x509.CertificateRevocationListBuilder()
    builder = builder.issuer_name(ca_name)
    if expired:
        builder = builder.last_update(now - timedelta(days=10))
        builder = builder.next_update(now - timedelta(days=2))
    else:
        builder = builder.last_update(now)
        builder = builder.next_update(now + timedelta(days=7))

    builder = builder.add_extension(x509.CRLNumber(crl_number), critical=False)

    if revoked_serials:
        for s in revoked_serials:
            r = (
                x509.RevokedCertificateBuilder()
                .serial_number(s)
                .revocation_date(now - timedelta(days=1))
                .build()
            )
            builder = builder.add_revoked_certificate(r)

    crl = builder.sign(ca_key, hashes.SHA256())
    return crl.public_bytes(serialization.Encoding.DER)


def test_crl_sync_and_revocation_update(crl_db):
    ca_pem, ca_key, ca_name, client_pem, client_serial = _create_ca_and_cert()
    register_certificate(crl_db, client_pem)

    # Initial state is GOOD
    cert_rec = crl_db.scalars(
        select(CertificateRecord).where(CertificateRecord.serial_number == str(client_serial))
    ).first()
    assert cert_rec.revocation_status == "GOOD"

    # Sync CRL sequence 1 with client_serial revoked
    crl_bytes = _build_crl(ca_key, ca_name, crl_number=1, revoked_serials=[client_serial])
    res = sync_crl(crl_db, crl_bytes, ca_pem, operator_username="admin")

    assert res.status == "GOOD_AS_OF_LAST_SYNC"
    assert res.crl_number == 1
    assert res.revoked_count == 1
    assert res.signature_valid is True

    # Confirm matching certificate in DB was flipped to REVOKED
    crl_db.refresh(cert_rec)
    assert cert_rec.revocation_status == "REVOKED"


def test_anti_rollback_protection(crl_db):
    ca_pem, ca_key, ca_name, _, client_serial = _create_ca_and_cert()

    # 1. Sync CRL #5
    crl_5 = _build_crl(ca_key, ca_name, crl_number=5, revoked_serials=[client_serial])
    res5 = sync_crl(crl_db, crl_5, ca_pem, operator_username="admin")
    assert res5.crl_number == 5
    assert res5.is_rollback is False

    # 2. Attacker attempts to replay older CRL #3
    crl_3 = _build_crl(ca_key, ca_name, crl_number=3, revoked_serials=[])
    res3 = sync_crl(crl_db, crl_3, ca_pem, operator_username="admin")
    assert res3.status == "ROLLBACK_ATTEMPT"
    assert res3.is_rollback is True
    assert "Rollback attack rejected" in res3.error

    # 3. Attacker replays duplicate sequence CRL #5
    res5_replay = sync_crl(crl_db, crl_5, ca_pem, operator_username="admin")
    assert res5_replay.status == "ROLLBACK_ATTEMPT"
    assert res5_replay.is_rollback is True


def test_reject_crl_invalid_signature(crl_db):
    ca_pem, _, ca_name, _, _ = _create_ca_and_cert()
    rogue_ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Rogue signed CRL
    crl_bytes = _build_crl(rogue_ca_key, ca_name, crl_number=10)
    res = sync_crl(crl_db, crl_bytes, ca_pem, operator_username="admin")

    assert res.status == "SIGNATURE_INVALID"
    assert res.signature_valid is False
    assert "signature verification failed" in res.error.lower()


def test_expired_crl_detection(crl_db):
    ca_pem, ca_key, ca_name, _, _ = _create_ca_and_cert()
    crl_bytes = _build_crl(ca_key, ca_name, crl_number=20, expired=True)

    res = sync_crl(crl_db, crl_bytes, ca_pem, operator_username="admin")
    assert res.status == "CRL_EXPIRED"
    assert res.signature_valid is True


def test_check_revocation_against_crl_cached(crl_db):
    ca_pem, ca_key, ca_name, _, client_serial = _create_ca_and_cert()
    crl_bytes = _build_crl(ca_key, ca_name, crl_number=1, revoked_serials=[client_serial])
    sync_crl(crl_db, crl_bytes, ca_pem, operator_username="admin")

    # Check revoked serial
    rev_info = check_revocation_against_crl(crl_db, ca_name.rfc4514_string(), str(client_serial))
    assert rev_info["revoked"] is True
    assert rev_info["status"] == "REVOKED"

    # Check unrevoked serial
    good_info = check_revocation_against_crl(crl_db, ca_name.rfc4514_string(), "999999")
    assert good_info["revoked"] is False
    assert good_info["status"] == "GOOD_AS_OF_LAST_SYNC"
