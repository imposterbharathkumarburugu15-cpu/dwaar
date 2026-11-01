"""Pramana Intelligence Systems API: Regulatory 2.0, Risk, Cross-Doc, Offline, Audit, & Assistant.

Exposes comprehensive government-grade intelligence services to the frontend:
- Regulatory Intelligence 2.0 (versioning & what-if simulation)
- Cross-Document Contradiction & Completeness Analysis
- Institutional Risk Intelligence & Sector Observatory
- Temporal Application Lifecycle & Backdating Anomaly Detection
- Drishti Grounded Investigation Assistant (Deficiency Drafting & Case Briefing)
- Offline Evidence Workspace (Bundle Export, Sync, & Reconciliation)
- Advanced Audit Engine (Full-chain Verification & Tamper Evidence Demonstration)
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..audit import export_verifiable_audit_receipt, simulate_audit_tampering, verify_chain
from ..auth import OFFICIAL_ROLES, current_user, has_permission, load_application, require_permission, require_roles
from ..db import get_db
from ..drishti.investigation import draft_deficiency_notice, synthesize_investigation_brief
from ..history.lifecycle import analyze_application_lifecycle
from ..models import Application, Institution, User
from ..offline.manager import build_offline_bundle, process_offline_sync, reconcile_offline_conflicts
from ..pipeline.cross_doc import run_cross_document_intelligence
from ..risk.engine import assess_institutional_risk, compute_sector_risk_observatory
from ..rules.simulator import run_simulation
from ..rules.versioning import compare_rulesets, list_available_rulesets

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


# =====================================================================
# 1. Regulatory Intelligence 2.0
# =====================================================================

@router.get("/regulatory/rulesets")
def get_rulesets(user: User = Depends(current_user)):
    """Lists all available versioned rulesets."""
    return list_available_rulesets()


@router.get("/regulatory/compare")
def diff_rulesets(
    v1: str = Query(..., description="First version or filename"),
    v2: str = Query(..., description="Second version or filename"),
    user: User = Depends(current_user),
):
    """Compares two ruleset versions and produces a structured diff."""
    return compare_rulesets(v1, v2)


class SimulationRequest(BaseModel):
    target_ruleset_version: str | None = None
    parameter_overrides: dict[str, Any] = {}
    application_id: str | None = None


@router.post("/regulatory/simulate")
def simulate_regulatory_changes(
    body: SimulationRequest,
    user: User = Depends(require_roles(*OFFICIAL_ROLES)),
    db: Session = Depends(get_db),
):
    """Executes a what-if simulation across applications with parameter overrides."""
    return run_simulation(
        db,
        target_ruleset_version=body.target_ruleset_version,
        parameter_overrides=body.parameter_overrides,
        application_id=body.application_id,
    )


# =====================================================================
# 2. Cross-Document Intelligence
# =====================================================================

@router.get("/applications/{app_id}/cross-doc")
def get_cross_document_intelligence(
    app_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Retrieves completeness analysis and cross-document contradictory claims."""
    load_application(db, user, app_id)
    return run_cross_document_intelligence(db, app_id)


# =====================================================================
# 3. Institutional Risk Intelligence
# =====================================================================

@router.get("/risk/institution/{institution_id}")
def get_institutional_risk(
    institution_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Retrieves an institution's composite risk tier and explainable factor breakdown."""
    if user.role not in OFFICIAL_ROLES and user.institution_id != institution_id:
        raise HTTPException(403, "Forbidden")
    return assess_institutional_risk(db, institution_id)


@router.get("/risk/observatory")
def get_sector_risk_observatory(
    user: User = Depends(require_roles(*OFFICIAL_ROLES)),
    db: Session = Depends(get_db),
):
    """Sector-wide risk intelligence aggregates across all institutions."""
    return compute_sector_risk_observatory(db)


# =====================================================================
# 4. Temporal Lifecycle Intelligence
# =====================================================================

@router.get("/applications/{app_id}/lifecycle")
def get_application_lifecycle(
    app_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Returns application historical event timeline and temporal backdating audit."""
    load_application(db, user, app_id)
    return analyze_application_lifecycle(db, app_id)


# =====================================================================
# 5. AI Investigation Assistant (Drishti)
# =====================================================================

@router.get("/applications/{app_id}/investigation-brief")
def get_investigation_brief(
    app_id: str,
    user: User = Depends(require_roles(*OFFICIAL_ROLES)),
    db: Session = Depends(get_db),
):
    """Synthesizes an executive investigative case brief with evidence citations."""
    load_application(db, user, app_id)
    return synthesize_investigation_brief(db, app_id)


@router.post("/applications/{app_id}/deficiency-draft")
def draft_deficiency_letter(
    app_id: str,
    user: User = Depends(require_roles(*OFFICIAL_ROLES)),
    db: Session = Depends(get_db),
):
    """Auto-drafts a formal deficiency notice citing exact handbook clauses."""
    load_application(db, user, app_id)
    return draft_deficiency_notice(db, app_id, user)


# =====================================================================
# 6. Offline Evidence Workspace
# =====================================================================

@router.get("/offline/bundle/{app_id}")
def export_offline_case_bundle(
    app_id: str,
    user: User = Depends(require_roles(*OFFICIAL_ROLES)),
    db: Session = Depends(get_db),
):
    """Exports a self-contained offline investigation case bundle for field visits."""
    load_application(db, user, app_id)
    return build_offline_bundle(db, app_id, user.username)


class OfflineSyncPayload(BaseModel):
    bundle_metadata: dict[str, Any]
    local_annotations: list[dict[str, Any]] = []
    checklist_updates: list[dict[str, Any]] = []


@router.post("/offline/sync")
def sync_offline_case_data(
    body: OfflineSyncPayload,
    user: User = Depends(require_roles(*OFFICIAL_ROLES)),
    db: Session = Depends(get_db),
):
    """Ingests offline observations and runs conflict detection against server state."""
    return process_offline_sync(
        db,
        bundle_meta=body.bundle_metadata,
        local_annotations=body.local_annotations,
        checklist_updates=body.checklist_updates,
        officer_username=user.username,
    )


class ConflictReconciliationPayload(BaseModel):
    application_id: str
    resolutions: list[dict[str, Any]]


@router.post("/offline/reconcile")
def reconcile_conflicts(
    body: ConflictReconciliationPayload,
    user: User = Depends(require_roles(*OFFICIAL_ROLES)),
    db: Session = Depends(get_db),
):
    """Applies manual officer reconciliation decisions to conflicted fields."""
    return reconcile_offline_conflicts(
        db,
        app_id=body.application_id,
        resolutions=body.resolutions,
        officer_username=user.username,
    )


# =====================================================================
# 7. Advanced Audit Engine
# =====================================================================

@router.get("/audit/verify-chain")
def get_audit_chain_verification(
    user: User = Depends(require_roles(*OFFICIAL_ROLES)),
    db: Session = Depends(get_db),
):
    """Full-chain SHA-256 hash continuity and Ed25519 signature checkpoint verification."""
    return verify_chain(db)


class TamperSimulationRequest(BaseModel):
    sequence_number: int | None = None


@router.post("/audit/simulate-tamper")
def simulate_audit_tamper(
    body: TamperSimulationRequest,
    user: User = Depends(require_roles(*OFFICIAL_ROLES)),
    db: Session = Depends(get_db),
):
    """Demonstrates tamper detection: verifies that 1-byte alteration breaks the hash chain."""
    return simulate_audit_tampering(db, target_seq=body.sequence_number)


@router.get("/audit/receipt/{app_id}")
def get_audit_receipt(
    app_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Exports a verifiable cryptographic audit receipt for an application."""
    load_application(db, user, app_id)
    return export_verifiable_audit_receipt(db, app_id)
