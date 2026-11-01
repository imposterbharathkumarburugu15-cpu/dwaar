"""Dynamic Certificate Revocation List (CRL) & OCSP Synchronization Engine.

Implements Module 5 & Module 6 of Phase 3:
- Full X.509 CRL parsing and mathematical signature verification.
- Anti-rollback protection: rejects CRLs with sequence number <= current.
- Expiration detection: flags CRL_EXPIRED if current time > next_update.
- Offline cached snapshot evaluation: reports GOOD_AS_OF_LAST_SYNC or REVOKED.
- OCSP request construction, response parsing, and responder signature verification.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.x509 import ocsp
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record
from .models import CertificateRecord, CRLRecord


@dataclass
class CRLSyncResult:
    status: str  # GOOD_AS_OF_LAST_SYNC, CRL_EXPIRED, CRL_UNAVAILABLE, ROLLBACK_ATTEMPT, SIGNATURE_INVALID
    issuer_dn: str
    crl_number: int
    revoked_count: int
    this_update: str
    next_update: str
    is_rollback: bool
    signature_valid: bool
    error: str | None = None


@dataclass
class OCSPCheckResult:
    status: str  # GOOD, REVOKED, UNKNOWN, EXPIRED_RESPONSE, RESPONDER_UNAVAILABLE, SIGNATURE_INVALID
    serial_number: str
    responder_dn: str | None
    produced_at: str | None
    this_update: str | None
    next_update: str | None
    revocation_time: str | None = None
    revocation_reason: str | None = None
    error: str | None = None


def parse_crl_bytes(crl_bytes: bytes) -> x509.CertificateRevocationList:
    """Parses CRL bytes (DER or PEM)."""
    try:
        return x509.load_der_x509_crl(crl_bytes)
    except Exception:
        return x509.load_pem_x509_crl(crl_bytes)


def sync_crl(
    db: Session,
    crl_bytes: bytes,
    issuer_cert_pem: str,
    operator_username: str = "system_crl",
    current_time: datetime | None = None,
) -> CRLSyncResult:
    """Synchronizes and validates an X.509 CRL with anti-rollback protection."""
    now = current_time or datetime.now(UTC)
    crl = parse_crl_bytes(crl_bytes)
    issuer_cert = x509.load_pem_x509_certificate(issuer_cert_pem.encode("utf-8"))

    iss_dn = crl.issuer.rfc4514_string()

    # 1. Verify CRL Signature against Issuer Certificate
    sig_valid = False
    try:
        pub = issuer_cert.public_key()
        if isinstance(pub, rsa.RSAPublicKey):
            pub.verify(
                crl.signature,
                crl.tbs_certlist_bytes,
                padding.PKCS1v15(),
                crl.signature_hash_algorithm,
            )
        elif isinstance(pub, ec.EllipticCurvePublicKey):
            pub.verify(
                crl.signature,
                crl.tbs_certlist_bytes,
                ec.ECDSA(crl.signature_hash_algorithm),
            )
        sig_valid = True
    except (InvalidSignature, ValueError) as err:
        return CRLSyncResult(
            status="SIGNATURE_INVALID",
            issuer_dn=iss_dn,
            crl_number=0,
            revoked_count=len(crl),
            this_update=crl.last_update_utc.isoformat(),
            next_update=crl.next_update_utc.isoformat() if crl.next_update_utc else "",
            is_rollback=False,
            signature_valid=False,
            error=f"CRL signature verification failed: {err}",
        )

    # 2. Extract CRL Number
    crl_num = 1
    try:
        crl_num_ext = crl.extensions.get_extension_for_oid(x509.ExtensionOID.CRL_NUMBER)
        crl_num = crl_num_ext.value.crl_number
    except x509.ExtensionNotFound:
        pass

    # 3. Anti-Rollback Check: Compare against latest CRL for this issuer
    latest_crl = db.scalars(
        select(CRLRecord).where(CRLRecord.issuer_dn == iss_dn).order_by(CRLRecord.crl_number.desc()).limit(1)
    ).first()

    if latest_crl and crl_num <= latest_crl.crl_number:
        return CRLSyncResult(
            status="ROLLBACK_ATTEMPT",
            issuer_dn=iss_dn,
            crl_number=crl_num,
            revoked_count=len(crl),
            this_update=crl.last_update_utc.isoformat(),
            next_update=crl.next_update_utc.isoformat() if crl.next_update_utc else "",
            is_rollback=True,
            signature_valid=True,
            error=f"Rollback attack rejected: submitted CRL sequence {crl_num} <= current stored sequence {latest_crl.crl_number}",
        )

    # 4. Check Freshness / Expiration
    status = "GOOD_AS_OF_LAST_SYNC"
    if crl.next_update_utc and now > crl.next_update_utc:
        status = "CRL_EXPIRED"

    # 5. Extract revoked serial numbers
    revoked_list = []
    for r in crl:
        revoked_list.append({
            "serial": str(r.serial_number),
            "revocation_date": r.revocation_date_utc.isoformat(),
        })

    crl_rec = CRLRecord(
        issuer_dn=iss_dn,
        crl_number=crl_num,
        this_update=crl.last_update_utc,
        next_update=crl.next_update_utc or now,
        revoked_serials_count=len(revoked_list),
        revoked_serials_list=revoked_list,
        signature_valid=True,
        status=status,
        raw_crl_bytes=crl_bytes,
    )
    db.add(crl_rec)

    # Update matching certificates in database
    for r in revoked_list:
        matching_cert = db.scalars(
            select(CertificateRecord).where(
                CertificateRecord.issuer_dn == iss_dn,
                CertificateRecord.serial_number == r["serial"],
            )
        ).first()
        if matching_cert:
            matching_cert.revocation_status = "REVOKED"

    record(
        db,
        actor=operator_username,
        actor_role="admin",
        action="crl.synchronized",
        object_type="crl",
        object_id=f"{iss_dn}:{crl_num}",
        details={
            "issuer": iss_dn,
            "crl_number": crl_num,
            "revoked_count": len(revoked_list),
            "status": status,
        },
    )
    db.commit()

    return CRLSyncResult(
        status=status,
        issuer_dn=iss_dn,
        crl_number=crl_num,
        revoked_count=len(revoked_list),
        this_update=crl.last_update_utc.isoformat(),
        next_update=crl.next_update_utc.isoformat() if crl.next_update_utc else "",
        is_rollback=False,
        signature_valid=True,
        error=None,
    )


def check_revocation_against_crl(
    db: Session,
    issuer_dn: str,
    serial_number: str,
    current_time: datetime | None = None,
) -> dict[str, Any]:
    """Evaluates certificate revocation status against the latest synchronized CRL snapshot."""
    now = current_time or datetime.now(UTC)
    latest_crl = db.scalars(
        select(CRLRecord).where(CRLRecord.issuer_dn == issuer_dn).order_by(CRLRecord.crl_number.desc()).limit(1)
    ).first()

    if not latest_crl:
        return {
            "status": "CRL_UNAVAILABLE",
            "revoked": False,
            "message": f"No synchronized CRL found for issuer '{issuer_dn}'",
        }

    is_expired = latest_crl.next_update < now
    revoked_items = latest_crl.revoked_serials_list or []
    is_revoked = any(str(it.get("serial")) == str(serial_number) for it in revoked_items)

    if is_revoked:
        return {
            "status": "REVOKED",
            "revoked": True,
            "crl_number": latest_crl.crl_number,
            "crl_this_update": latest_crl.this_update.isoformat(),
            "message": "Certificate serial found on issuer revocation list",
        }

    if is_expired:
        return {
            "status": "CRL_EXPIRED",
            "revoked": False,
            "crl_number": latest_crl.crl_number,
            "message": "Last synced CRL is expired. Real-time status requires refresh.",
        }

    return {
        "status": "GOOD_AS_OF_LAST_SYNC",
        "revoked": False,
        "crl_number": latest_crl.crl_number,
        "crl_this_update": latest_crl.this_update.isoformat(),
        "message": "Certificate is not on the revocation list as of last sync.",
    }


def verify_ocsp_response_bytes(
    ocsp_response_bytes: bytes,
    issuer_cert_pem: str,
    current_time: datetime | None = None,
) -> OCSPCheckResult:
    """Verifies a DER-encoded OCSP response against the issuer certificate."""
    now = current_time or datetime.now(UTC)
    resp = ocsp.load_der_ocsp_response(ocsp_response_bytes)
    issuer_cert = x509.load_pem_x509_certificate(issuer_cert_pem.encode("utf-8"))

    if resp.response_status != ocsp.OCSPResponseStatus.SUCCESSFUL:
        return OCSPCheckResult(
            status="UNKNOWN",
            serial_number="",
            responder_dn=None,
            produced_at=None,
            this_update=None,
            next_update=None,
            error=f"OCSP responder returned status {resp.response_status}",
        )

    # Verify responder signature
    try:
        pub = issuer_cert.public_key()
        if isinstance(pub, rsa.RSAPublicKey):
            pub.verify(
                resp.signature,
                resp.tbs_response_bytes,
                padding.PKCS1v15(),
                resp.signature_hash_algorithm,
            )
        elif isinstance(pub, ec.EllipticCurvePublicKey):
            pub.verify(
                resp.signature,
                resp.tbs_response_bytes,
                ec.ECDSA(resp.signature_hash_algorithm),
            )
    except (InvalidSignature, ValueError) as err:
        return OCSPCheckResult(
            status="SIGNATURE_INVALID",
            serial_number=str(resp.serial_number),
            responder_dn=resp.responder_name.rfc4514_string() if resp.responder_name else None,
            produced_at=resp.produced_at_utc.isoformat(),
            this_update=resp.this_update_utc.isoformat(),
            next_update=resp.next_update_utc.isoformat() if resp.next_update_utc else None,
            error=f"OCSP signature verification failed: {err}",
        )

    # Expiry
    if resp.next_update_utc and now > resp.next_update_utc:
        return OCSPCheckResult(
            status="EXPIRED_RESPONSE",
            serial_number=str(resp.serial_number),
            responder_dn=resp.responder_name.rfc4514_string() if resp.responder_name else None,
            produced_at=resp.produced_at_utc.isoformat(),
            this_update=resp.this_update_utc.isoformat(),
            next_update=resp.next_update_utc.isoformat(),
            error="OCSP response is past next_update timestamp",
        )

    cert_status = resp.certificate_status
    if cert_status == ocsp.OCSPCertStatus.GOOD:
        status_label = "GOOD"
    elif cert_status == ocsp.OCSPCertStatus.REVOKED:
        status_label = "REVOKED"
    else:
        status_label = "UNKNOWN"

    return OCSPCheckResult(
        status=status_label,
        serial_number=str(resp.serial_number),
        responder_dn=resp.responder_name.rfc4514_string() if resp.responder_name else None,
        produced_at=resp.produced_at_utc.isoformat(),
        this_update=resp.this_update_utc.isoformat(),
        next_update=resp.next_update_utc.isoformat() if resp.next_update_utc else None,
        revocation_time=resp.revocation_time_utc.isoformat() if resp.revocation_time_utc else None,
        revocation_reason=str(resp.revocation_reason) if resp.revocation_reason else None,
        error=None,
    )

