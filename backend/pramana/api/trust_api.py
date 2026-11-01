"""FastAPI router for PRAMANA Hardware Security and Trust Infrastructure.

Mounts under /api/trust.
"""

import base64
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import User, current_user, require_roles
from ..db import get_db
from ..trust.certificates import parse_certificate_pem, register_certificate, validate_certificate
from ..trust.crl_ocsp import check_revocation_against_crl, sync_crl, verify_ocsp_response_bytes
from ..trust.hsm import default_hsm_registry
from ..trust.incident import execute_incident_recovery, raise_security_incident
from ..trust.kms import kms_service
from ..trust.models import CertificateRecord, CRLRecord, CryptographicKey, SecurityIncident
from ..trust.trust_store import default_trust_store

router = APIRouter(prefix="/api/trust", tags=["trust-infrastructure"])

TRUST_ADMIN_ROLES = ("super_admin", "aicte_admin", "admin")


# --- Pydantic Payloads ---

class GenerateKeyPayload(BaseModel):
    key_id: str
    algorithm: str  # Ed25519, ECDSA_P256, AES_256_GCM
    key_purpose: str
    provider_type: str = "DEVELOPMENT_PROVIDER"
    metadata: dict[str, Any] = {}


class RotateKeyPayload(BaseModel):
    rotation_reason: str
    grace_period_days: int = 30


class RevokeKeyPayload(BaseModel):
    reason: str


class RegisterCertPayload(BaseModel):
    certificate_pem: str
    trust_status: str = "UNTRUSTED"


class ValidateCertPayload(BaseModel):
    certificate_pem: str
    environment: str = "development"


class SyncCRLPayload(BaseModel):
    crl_bytes_b64: str
    issuer_cert_pem: str


class VerifyOCSPPayload(BaseModel):
    ocsp_response_b64: str
    issuer_cert_pem: str


class AddTrustAnchorPayload(BaseModel):
    certificate_id: str
    environment: str = "development"


class RaiseIncidentPayload(BaseModel):
    incident_type: str
    description: str
    affected_key_id: str | None = None
    severity: str = "HIGH"


class RecoverIncidentPayload(BaseModel):
    generate_replacement_key: bool = True
    resolution_notes: str = "Key compromise contained and replacement key issued."


# --- KMS Endpoints ---

@router.get("/keys")
def list_cryptographic_keys(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Lists all KMS keys with safe metadata (private keys are NEVER exposed)."""
    keys = list(db.scalars(select(CryptographicKey).order_by(CryptographicKey.created_at.desc())).all())
    return [
        {
            "id": k.id,
            "key_id": k.key_id,
            "algorithm": k.algorithm,
            "key_purpose": k.key_purpose,
            "provider_type": k.provider_type,
            "status": k.status,
            "version": k.version,
            "public_key_fingerprint": k.public_key_fingerprint,
            "created_at": k.created_at.isoformat(),
            "activated_at": k.activated_at.isoformat() if k.activated_at else None,
            "usage_count": k.usage_count,
        }
        for k in keys
    ]


@router.post("/keys")
def create_cryptographic_key(
    body: GenerateKeyPayload,
    user: User = Depends(require_roles(*TRUST_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """Generates a new cryptographic key managed by the KMS."""
    try:
        key_rec = kms_service.generate_key(
            db=db,
            key_id=body.key_id,
            algorithm=body.algorithm,
            key_purpose=body.key_purpose,
            provider_type=body.provider_type,
            metadata=body.metadata,
            operator_username=user.username,
        )
        return {
            "key_id": key_rec.key_id,
            "algorithm": key_rec.algorithm,
            "status": key_rec.status,
            "version": key_rec.version,
            "public_key_b64": key_rec.public_key_b64,
            "public_key_fingerprint": key_rec.public_key_fingerprint,
        }
    except ValueError as err:
        raise HTTPException(status.HTTP_409_CONFLICT, str(err))


@router.get("/keys/{key_id}")
def get_key_details(
    key_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Retrieves safe public metadata and verification parameters for a key."""
    key_rec = db.scalars(select(CryptographicKey).where(CryptographicKey.key_id == key_id)).first()
    if not key_rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Key '{key_id}' not found")

    return {
        "key_id": key_rec.key_id,
        "algorithm": key_rec.algorithm,
        "key_purpose": key_rec.key_purpose,
        "provider_type": key_rec.provider_type,
        "status": key_rec.status,
        "version": key_rec.version,
        "public_key_b64": key_rec.public_key_b64,
        "public_key_fingerprint": key_rec.public_key_fingerprint,
        "created_at": key_rec.created_at.isoformat(),
        "usage_count": key_rec.usage_count,
        "metadata": key_rec.metadata_json,
    }


@router.post("/keys/{key_id}/rotate")
def rotate_cryptographic_key(
    key_id: str,
    body: RotateKeyPayload,
    user: User = Depends(require_roles(*TRUST_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """Rotates key version while preserving historical public key verification."""
    try:
        old_k, new_k = kms_service.rotate_key(
            db=db,
            key_id=key_id,
            rotation_reason=body.rotation_reason,
            operator_username=user.username,
            grace_period_days=body.grace_period_days,
        )
        return {
            "status": "rotated",
            "old_key_id": old_k.key_id,
            "old_key_status": old_k.status,
            "new_key_id": new_k.key_id,
            "new_key_status": new_k.status,
            "new_version": new_k.version,
        }
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err))


@router.post("/keys/{key_id}/revoke")
def revoke_cryptographic_key(
    key_id: str,
    body: RevokeKeyPayload,
    user: User = Depends(require_roles(*TRUST_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """Revokes a key."""
    try:
        key_rec = kms_service.transition_status(
            db=db,
            key_id=key_id,
            new_status="REVOKED",
            operator_username=user.username,
            reason=body.reason,
        )
        return {"key_id": key_rec.key_id, "status": key_rec.status}
    except ValueError as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(err))


# --- HSM Endpoints ---

@router.get("/hsm/health")
def get_hsm_health(
    provider_type: str = "DEVELOPMENT_PROVIDER",
    user: User = Depends(current_user),
):
    """Returns honest HSM provider diagnostics and capability status."""
    provider = default_hsm_registry.get_provider(provider_type)
    health = provider.check_health()
    return {
        "healthy": health.healthy,
        "provider_type": health.provider_type,
        "is_hardware_backed": health.is_hardware_backed,
        "capabilities": health.capabilities,
        "status_message": health.status_message,
        "checked_at": health.checked_at,
        "diagnostics": health.diagnostics,
    }


# --- Certificate Endpoints ---

@router.get("/certificates")
def list_certificates(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Lists registered X.509 certificates and trust anchors."""
    certs = list(db.scalars(select(CertificateRecord).order_by(CertificateRecord.created_at.desc())).all())
    return [
        {
            "id": c.id,
            "serial_number": c.serial_number,
            "issuer_dn": c.issuer_dn,
            "subject_dn": c.subject_dn,
            "fingerprint_sha256": c.fingerprint_sha256,
            "not_before": c.not_before.isoformat(),
            "not_after": c.not_after.isoformat(),
            "trust_status": c.trust_status,
            "revocation_status": c.revocation_status,
        }
        for c in certs
    ]


@router.post("/certificates")
def register_x509_certificate(
    body: RegisterCertPayload,
    user: User = Depends(require_roles(*TRUST_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """Registers an X.509 certificate."""
    try:
        rec = register_certificate(db, body.certificate_pem, trust_status=body.trust_status)
        return {
            "id": rec.id,
            "subject_dn": rec.subject_dn,
            "serial_number": rec.serial_number,
            "fingerprint_sha256": rec.fingerprint_sha256,
            "trust_status": rec.trust_status,
        }
    except Exception as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Certificate registration failed: {err}")


@router.post("/certificates/validate")
def validate_x509_certificate(
    body: ValidateCertPayload,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Validates an X.509 certificate against trust anchors and validity periods."""
    res = validate_certificate(db, body.certificate_pem, environment=body.environment)
    return {
        "status": res.status,
        "valid": res.valid,
        "subject_dn": res.subject_dn,
        "issuer_dn": res.issuer_dn,
        "serial_number": res.serial_number,
        "days_until_expiry": res.days_until_expiry,
        "is_trust_anchor": res.is_trust_anchor,
        "error": res.error,
        "warnings": res.warnings,
    }


# --- CRL & OCSP Endpoints ---

@router.post("/crl/sync")
def sync_certificate_revocation_list(
    body: SyncCRLPayload,
    user: User = Depends(require_roles(*TRUST_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """Synchronizes an X.509 CRL with anti-rollback protection."""
    try:
        crl_bytes = base64.b64decode(body.crl_bytes_b64)
        res = sync_crl(db, crl_bytes, body.issuer_cert_pem, operator_username=user.username)
        return {
            "status": res.status,
            "issuer_dn": res.issuer_dn,
            "crl_number": res.crl_number,
            "revoked_count": res.revoked_count,
            "this_update": res.this_update,
            "next_update": res.next_update,
            "signature_valid": res.signature_valid,
            "error": res.error,
        }
    except Exception as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"CRL synchronization failed: {err}")


@router.post("/ocsp/verify")
def verify_ocsp_response(
    body: VerifyOCSPPayload,
    user: User = Depends(current_user),
):
    """Verifies a DER-encoded OCSP response against issuer certificate."""
    try:
        resp_bytes = base64.b64decode(body.ocsp_response_b64)
        res = verify_ocsp_response_bytes(resp_bytes, body.issuer_cert_pem)
        return {
            "status": res.status,
            "serial_number": res.serial_number,
            "responder_dn": res.responder_dn,
            "this_update": res.this_update,
            "next_update": res.next_update,
            "revocation_time": res.revocation_time,
            "error": res.error,
        }
    except Exception as err:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"OCSP verification failed: {err}")


# --- Trust Store Endpoints ---

@router.get("/anchors")
def list_trust_anchors(
    environment: str = "development",
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Lists trusted roots for an environment."""
    return default_trust_store.list_trust_anchors(db, environment=environment)


@router.post("/anchors")
def add_trust_anchor(
    body: AddTrustAnchorPayload,
    user: User = Depends(require_roles(*TRUST_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """Registers a certificate as a trust anchor."""
    try:
        entry = default_trust_store.add_trust_anchor(
            db, body.certificate_id, environment=body.environment, operator_username=user.username
        )
        return {"entry_id": entry.id, "environment": entry.environment, "version": entry.trust_store_version}
    except ValueError as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(err))


# --- Security Incident Endpoints ---

@router.get("/incidents")
def list_security_incidents(
    user: User = Depends(require_roles(*TRUST_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """Lists security incidents."""
    incidents = list(db.scalars(select(SecurityIncident).order_by(SecurityIncident.reported_at.desc())).all())
    return [
        {
            "id": i.id,
            "incident_type": i.incident_type,
            "affected_key_id": i.affected_key_id,
            "severity": i.severity,
            "description": i.description,
            "status": i.status,
            "actions_taken": i.actions_taken,
            "reported_by": i.reported_by,
            "reported_at": i.reported_at.isoformat(),
            "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
        }
        for i in incidents
    ]


@router.post("/incidents")
def create_security_incident(
    body: RaiseIncidentPayload,
    user: User = Depends(require_roles(*TRUST_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """Raises a security incident and automatically suspends affected keys."""
    inc = raise_security_incident(
        db=db,
        incident_type=body.incident_type,
        description=body.description,
        reported_by=user.username,
        affected_key_id=body.affected_key_id,
        severity=body.severity,
    )
    return {
        "id": inc.id,
        "incident_type": inc.incident_type,
        "status": inc.status,
        "affected_key_id": inc.affected_key_id,
        "actions_taken": inc.actions_taken,
    }


@router.post("/incidents/{incident_id}/recover")
def recover_security_incident(
    incident_id: str,
    body: RecoverIncidentPayload,
    user: User = Depends(require_roles(*TRUST_ADMIN_ROLES)),
    db: Session = Depends(get_db),
):
    """Executes key compromise recovery workflow."""
    try:
        return execute_incident_recovery(
            db=db,
            incident_id=incident_id,
            operator_username=user.username,
            generate_replacement_key=body.generate_replacement_key,
            resolution_notes=body.resolution_notes,
        )
    except ValueError as err:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(err))

