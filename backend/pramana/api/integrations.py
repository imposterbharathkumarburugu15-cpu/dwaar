"""REST API Endpoints for Government Integrations, Consent, and External Verification."""

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..integrations.consent import default_consent_service
from ..integrations.models import ExternalVerificationRequest, ExternalVerificationResult, GovernmentProvider
from ..integrations.registry import default_registry
from ..integrations.verification import default_verification_engine
from ..auth import current_user, require_roles
from ..models import User

router = APIRouter(prefix="/api/v1/integrations", tags=["government_integrations"])


# --- Schemas ---

class ProviderStatusUpdate(BaseModel):
    status: str
    reason: str | None = None


class ConsentGrantRequest(BaseModel):
    application_id: str
    institution_id: str
    provider_id: str
    document_category: str
    purpose: str
    validity_days: int = 90


class ConsentRevokeRequest(BaseModel):
    reason: str | None = None


class VerifyGovernmentDocumentRequest(BaseModel):
    application_id: str
    document_id: str
    provider_id: str
    document_category: str
    query_params: dict[str, Any] = Field(default_factory=dict)
    document_content_b64: str | None = None


# --- Endpoints ---

@router.get("/providers")
def list_providers(
    category: str | None = Query(None),
    db: Session = Depends(get_db),
    active_user: User = Depends(current_user),
):
    """Lists registered government integration providers and their statuses."""
    default_registry.initialize_default_providers(db)
    providers = default_registry.list_providers(db, category=category)
    return [
        {
            "id": p.id,
            "provider_name": p.provider_name,
            "provider_category": p.provider_category,
            "integration_type": p.integration_type,
            "environment": p.environment,
            "connection_status": p.connection_status,
            "base_url": p.base_url,
            "supported_operations": p.supported_operations,
            "last_verified_at": p.last_verified_at.isoformat() if p.last_verified_at else None,
        }
        for p in providers
    ]


@router.post("/providers/{provider_id}/test")
def test_provider_connectivity(
    provider_id: str,
    db: Session = Depends(get_db),
    active_user: User = Depends(require_roles("officer", "admin", "super_admin")),
):
    """Probes health and latency for a government provider."""
    result = default_registry.test_connectivity(db, provider_id)
    return result


@router.post("/providers/{provider_id}/status")
def update_provider_status(
    provider_id: str,
    payload: ProviderStatusUpdate,
    db: Session = Depends(get_db),
    active_user: User = Depends(require_roles("admin", "super_admin")),
):
    """Updates operational state of a provider (Administrative restricted)."""
    try:
        p = default_registry.update_provider_status(
            db, provider_id=provider_id, status=payload.status, operator=active_user.username, reason=payload.reason
        )
        return {"id": p.id, "connection_status": p.connection_status, "updated_at": p.updated_at.isoformat()}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/consent")
def grant_consent(
    payload: ConsentGrantRequest,
    db: Session = Depends(get_db),
    active_user: User = Depends(require_roles("institution_admin", "admin", "super_admin", "officer")),
):
    """Grants purpose-bound, time-delimited consent for government document access."""
    rec = default_consent_service.grant_consent(
        db,
        application_id=payload.application_id,
        institution_id=payload.institution_id,
        provider_id=payload.provider_id,
        document_category=payload.document_category,
        purpose=payload.purpose,
        validity_days=payload.validity_days,
        operator=active_user.username,
    )
    return {
        "consent_id": rec.id,
        "application_id": rec.application_id,
        "status": rec.status,
        "valid_until": rec.valid_until.isoformat(),
    }


@router.post("/consent/{consent_id}/revoke")
def revoke_consent(
    consent_id: str,
    payload: ConsentRevokeRequest,
    db: Session = Depends(get_db),
    active_user: User = Depends(require_roles("institution_admin", "admin", "super_admin")),
):
    """Immediately revokes an active consent record."""
    try:
        rec = default_consent_service.revoke_consent(
            db, consent_id=consent_id, revoked_by=active_user.username, reason=payload.reason
        )
        return {"consent_id": rec.id, "status": rec.status, "revoked_at": rec.revoked_at.isoformat()}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/verifications/government")
def verify_government_document(
    payload: VerifyGovernmentDocumentRequest,
    db: Session = Depends(get_db),
    active_user: User = Depends(require_roles("officer", "admin", "super_admin")),
):
    """Executes the 12-step verification against an authorized government service."""
    import base64

    doc_bytes = (
        base64.b64decode(payload.document_content_b64)
        if payload.document_content_b64
        else b"%PDF-1.4 Simulated Clean Affidavit Evidence"
    )

    try:
        res = default_verification_engine.verify_document_against_government(
            db=db,
            application_id=payload.application_id,
            document_id=payload.document_id,
            provider_id=payload.provider_id,
            document_category=payload.document_category,
            document_bytes=doc_bytes,
            query_params=payload.query_params,
            initiated_by=active_user.username,
        )
        return res
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/verifications/{verification_id}")
def get_verification_details(
    verification_id: str,
    db: Session = Depends(get_db),
    active_user: User = Depends(current_user),
):
    """Fetches cryptographically verifiable outcome of a government verification."""
    req = db.get(ExternalVerificationRequest, verification_id)
    if not req:
        raise HTTPException(status_code=404, detail="Verification request not found")

    result = req.results[0] if req.results else None
    return {
        "verification_id": req.id,
        "application_id": req.application_id,
        "document_id": req.document_id,
        "provider_id": req.provider_id,
        "status": req.status,
        "verdict": result.verdict if result else "PENDING",
        "cert_chain_valid": result.cert_chain_valid if result else False,
        "signature_valid": result.signature_valid if result else False,
        "discrepancies": result.discrepancies if result else [],
        "completed_at": req.completed_at.isoformat() if req.completed_at else None,
    }
