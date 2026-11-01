"""Demonstration seeder for PRAMANA Hardware Security and Trust Infrastructure.

Seeds default cryptographic keys (Ed25519, ECDSA, AES-GCM), test certificates, and trust anchors.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import User
from .certificates import register_certificate
from .hsm import default_hsm_registry
from .kms import kms_service
from .models import CryptographicKey
from .trust_store import default_trust_store


def seed_trust_infrastructure(db: Session, admin_user: User) -> None:
    """Seeds initial KMS keys, X.509 root certificate, and trust anchors."""
    existing = db.scalars(select(CryptographicKey)).first()
    if existing:
        return

    # 1. Seed Core KMS Keys
    # Audit trail signing key
    kms_service.generate_key(
        db=db,
        key_id="prm-audit-ed25519-v1",
        algorithm="ED25519",
        key_purpose="audit_signing",
        metadata={"description": "Primary Merkle checkpoint signing key"},
        operator_username=admin_user.username,
    )

    # QR Token issuance key
    kms_service.generate_key(
        db=db,
        key_id="prm-qr-ed25519-v1",
        algorithm="ED25519",
        key_purpose="qr_issuance",
        metadata={"description": "Institutional JWS QR issuance key"},
        operator_username=admin_user.username,
    )

    # Document Envelope encryption key
    kms_service.generate_key(
        db=db,
        key_id="prm-envelope-aes256-v1",
        algorithm="AES_256_GCM",
        key_purpose="document_envelope",
        metadata={"description": "Per-document envelope master key"},
        operator_username=admin_user.username,
    )

    # ECDSA Regulatory Attestation key
    kms_service.generate_key(
        db=db,
        key_id="prm-regulatory-ecdsa-v1",
        algorithm="ECDSA_P256",
        key_purpose="officer_field_signing",
        metadata={"description": "Regulatory officer field attestation key"},
        operator_username=admin_user.username,
    )

    # 2. Generate and seed PRAMANA Self-Signed Root CA for Development
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "New Delhi"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "All India Council for Technical Education"),
        x509.NameAttribute(NameOID.COMMON_NAME, "PRAMANA Demonstration Root CA 2026"),
    ])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(priv.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=30))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(priv, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")

    cert_rec = register_certificate(db, cert_pem, trust_status="TRUSTED_ANCHOR")

    # 3. Add to Development and Test Trust Stores
    default_trust_store.add_trust_anchor(db, cert_rec.id, environment="development", operator_username=admin_user.username)
    default_trust_store.add_trust_anchor(db, cert_rec.id, environment="test", operator_username=admin_user.username)
