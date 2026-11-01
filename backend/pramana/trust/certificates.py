"""X.509 Certificate Lifecycle Management & Chain Validation.

Implements Module 4 of Phase 3:
- X.509 certificate parsing and metadata extraction using standard `cryptography.x509`.
- Validity period checking and expiration warnings.
- Trust anchor management and certificate chain validation.
- Clear status classification: VALID, EXPIRED, UNTRUSTED_ISSUER, INVALID_SIGNATURE, REVOKED.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..crypto import sha256_hex
from .models import CertificateRecord, TrustStoreEntry


@dataclass
class CertificateValidationResult:
    status: str  # VALID, EXPIRED, UNTRUSTED_ISSUER, INVALID_SIGNATURE, REVOKED
    valid: bool
    subject_dn: str
    issuer_dn: str
    serial_number: str
    fingerprint_sha256: str
    days_until_expiry: int
    is_self_signed: bool
    is_trust_anchor: bool
    error: str | None = None
    warnings: list[str] = None


def parse_certificate_pem(cert_pem: str) -> x509.Certificate:
    """Parses PEM-encoded X.509 certificate bytes."""
    return x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))


def register_certificate(
    db: Session,
    cert_pem: str,
    trust_status: str = "UNTRUSTED",
) -> CertificateRecord:
    """Parses and stores an X.509 certificate in the trust repository."""
    cert = parse_certificate_pem(cert_pem)
    sha256_fp = sha256_hex(cert.public_bytes(serialization.Encoding.DER))

    existing = db.scalars(select(CertificateRecord).where(CertificateRecord.fingerprint_sha256 == sha256_fp)).first()
    if existing:
        return existing

    # Extract CRL distribution points if present
    crl_dps = []
    try:
        crl_ext = cert.extensions.get_extension_for_oid(x509.ExtensionOID.CRL_DISTRIBUTION_POINTS)
        for dp in crl_ext.value:
            if dp.full_name:
                for name in dp.full_name:
                    crl_dps.append(str(name.value))
    except x509.ExtensionNotFound:
        pass

    # Extract OCSP responder URLs if present
    ocsp_urls = []
    try:
        aia_ext = cert.extensions.get_extension_for_oid(x509.ExtensionOID.AUTHORITY_INFORMATION_ACCESS)
        for desc in aia_ext.value:
            if desc.access_method == x509.AuthorityInformationAccessOID.OCSP:
                ocsp_urls.append(str(desc.access_location.value))
    except x509.ExtensionNotFound:
        pass

    rec = CertificateRecord(
        serial_number=str(cert.serial_number),
        issuer_dn=cert.issuer.rfc4514_string(),
        subject_dn=cert.subject.rfc4514_string(),
        fingerprint_sha256=sha256_fp,
        not_before=cert.not_valid_before_utc,
        not_after=cert.not_valid_after_utc,
        certificate_pem=cert_pem,
        trust_status=trust_status,
        revocation_status="GOOD",
        crl_distribution_points=crl_dps,
        ocsp_responder_urls=ocsp_urls,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def validate_certificate(
    db: Session,
    cert_pem: str,
    environment: str = "development",
    current_time: datetime | None = None,
) -> CertificateValidationResult:
    """Validates an X.509 certificate against validity periods, trust anchors, and signatures."""
    now = current_time or datetime.now(UTC)
    warnings: list[str] = []

    try:
        cert = parse_certificate_pem(cert_pem)
    except Exception as err:
        return CertificateValidationResult(
            status="INVALID_FORMAT",
            valid=False,
            subject_dn="Unknown",
            issuer_dn="Unknown",
            serial_number="Unknown",
            fingerprint_sha256="",
            days_until_expiry=0,
            is_self_signed=False,
            is_trust_anchor=False,
            error=f"Malformed X.509 PEM: {err}",
            warnings=[],
        )

    subj_dn = cert.subject.rfc4514_string()
    iss_dn = cert.issuer.rfc4514_string()
    serial = str(cert.serial_number)
    sha256_fp = sha256_hex(cert.public_bytes(serialization.Encoding.DER))
    is_self_signed = subj_dn == iss_dn

    # 1. Validity Period Check
    if now < cert.not_valid_before_utc:
        return CertificateValidationResult(
            status="NOT_YET_VALID",
            valid=False,
            subject_dn=subj_dn,
            issuer_dn=iss_dn,
            serial_number=serial,
            fingerprint_sha256=sha256_fp,
            days_until_expiry=int((cert.not_valid_after_utc - now).total_seconds() / 86400),
            is_self_signed=is_self_signed,
            is_trust_anchor=False,
            error=f"Certificate not valid before {cert.not_valid_before_utc.isoformat()}",
            warnings=warnings,
        )

    if now > cert.not_valid_after_utc:
        return CertificateValidationResult(
            status="EXPIRED",
            valid=False,
            subject_dn=subj_dn,
            issuer_dn=iss_dn,
            serial_number=serial,
            fingerprint_sha256=sha256_fp,
            days_until_expiry=0,
            is_self_signed=is_self_signed,
            is_trust_anchor=False,
            error=f"Certificate expired at {cert.not_valid_after_utc.isoformat()}",
            warnings=warnings,
        )

    days_left = int((cert.not_valid_after_utc - now).total_seconds() / 86400)
    if days_left < 30:
        warnings.append(f"Certificate expires soon ({days_left} days remaining)")

    # 2. Check Trust Store for Anchor
    anchor_entry = db.scalars(
        select(TrustStoreEntry)
        .join(CertificateRecord, TrustStoreEntry.certificate_id == CertificateRecord.id)
        .where(
            TrustStoreEntry.environment == environment,
            CertificateRecord.fingerprint_sha256 == sha256_fp,
            TrustStoreEntry.is_anchor.is_(True),
        )
    ).first()

    is_trust_anchor = anchor_entry is not None

    if is_self_signed and not is_trust_anchor:
        return CertificateValidationResult(
            status="UNTRUSTED_ISSUER",
            valid=False,
            subject_dn=subj_dn,
            issuer_dn=iss_dn,
            serial_number=serial,
            fingerprint_sha256=sha256_fp,
            days_until_expiry=days_left,
            is_self_signed=True,
            is_trust_anchor=False,
            error="Self-signed certificate is not registered as a trusted anchor in the trust store",
            warnings=warnings,
        )

    # 3. Signature Verification (self-signed verification or parent CA verification)
    try:
        if is_self_signed:
            pub = cert.public_key()
            _verify_cert_signature(cert, pub)
        else:
            # Find issuer in trust store
            issuer_cert_rec = db.scalars(
                select(CertificateRecord).where(CertificateRecord.subject_dn == iss_dn)
            ).first()
            if not issuer_cert_rec:
                return CertificateValidationResult(
                    status="UNTRUSTED_ISSUER",
                    valid=False,
                    subject_dn=subj_dn,
                    issuer_dn=iss_dn,
                    serial_number=serial,
                    fingerprint_sha256=sha256_fp,
                    days_until_expiry=days_left,
                    is_self_signed=False,
                    is_trust_anchor=False,
                    error=f"Issuer '{iss_dn}' not found in trust store",
                    warnings=warnings,
                )
            parent_cert = parse_certificate_pem(issuer_cert_rec.certificate_pem)
            _verify_cert_signature(cert, parent_cert.public_key())
    except (InvalidSignature, ValueError) as err:
        return CertificateValidationResult(
            status="INVALID_SIGNATURE",
            valid=False,
            subject_dn=subj_dn,
            issuer_dn=iss_dn,
            serial_number=serial,
            fingerprint_sha256=sha256_fp,
            days_until_expiry=days_left,
            is_self_signed=is_self_signed,
            is_trust_anchor=is_trust_anchor,
            error=f"Cryptographic signature check failed: {err}",
            warnings=warnings,
        )

    # 4. Check Local Revocation Status
    cert_rec = db.scalars(select(CertificateRecord).where(CertificateRecord.fingerprint_sha256 == sha256_fp)).first()
    if cert_rec and cert_rec.revocation_status == "REVOKED":
        return CertificateValidationResult(
            status="REVOKED",
            valid=False,
            subject_dn=subj_dn,
            issuer_dn=iss_dn,
            serial_number=serial,
            fingerprint_sha256=sha256_fp,
            days_until_expiry=days_left,
            is_self_signed=is_self_signed,
            is_trust_anchor=is_trust_anchor,
            error="Certificate has been formally revoked",
            warnings=warnings,
        )

    return CertificateValidationResult(
        status="VALID",
        valid=True,
        subject_dn=subj_dn,
        issuer_dn=iss_dn,
        serial_number=serial,
        fingerprint_sha256=sha256_fp,
        days_until_expiry=days_left,
        is_self_signed=is_self_signed,
        is_trust_anchor=is_trust_anchor,
        error=None,
        warnings=warnings,
    )


def _verify_cert_signature(cert: x509.Certificate, issuer_pub_key: Any) -> None:
    """Verifies that cert was signed by issuer_pub_key."""
    if isinstance(issuer_pub_key, rsa.RSAPublicKey):
        issuer_pub_key.verify(
            cert.signature,
            cert.tbs_certificate_bytes,
            padding.PKCS1v15(),
            cert.signature_hash_algorithm,
        )
    elif isinstance(issuer_pub_key, ec.EllipticCurvePublicKey):
        issuer_pub_key.verify(
            cert.signature,
            cert.tbs_certificate_bytes,
            ec.ECDSA(cert.signature_hash_algorithm),
        )
    elif isinstance(issuer_pub_key, ed25519.Ed25519PublicKey):
        issuer_pub_key.verify(
            cert.signature,
            cert.tbs_certificate_bytes,
        )
    else:
        raise ValueError("Unsupported public key algorithm for certificate validation")
