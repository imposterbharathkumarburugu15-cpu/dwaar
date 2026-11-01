"""Cryptographic Security Incident Management & Key Compromise Recovery.

Implements Module 8 of Phase 3:
- Security incident lifecycle (OPEN, INVESTIGATING, CONTAINED, RESOLVED).
- Immediate key compromise suspension and certificate revocation.
- Replacement key generation and rotation audit trail.
- Preservation of historical evidence for post-incident forensic inquiry.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record
from .kms import kms_service
from .models import CryptographicKey, SecurityIncident


def raise_security_incident(
    db: Session,
    incident_type: str,
    description: str,
    reported_by: str,
    affected_key_id: str | None = None,
    severity: str = "HIGH",
) -> SecurityIncident:
    """Logs a cryptographic incident and immediately isolates affected keys."""
    incident = SecurityIncident(
        incident_type=incident_type,
        affected_key_id=affected_key_id,
        severity=severity,
        description=description,
        status="OPEN",
        reported_by=reported_by,
        reported_at=datetime.now(UTC),
        actions_taken=[],
    )
    db.add(incident)
    db.flush()

    actions = []
    # If a key is explicitly affected, immediately suspend/compromise it
    if affected_key_id:
        key_rec = db.scalars(select(CryptographicKey).where(CryptographicKey.key_id == affected_key_id)).first()
        if key_rec and key_rec.status not in ("COMPROMISED", "REVOKED"):
            kms_service.transition_status(
                db=db,
                key_id=affected_key_id,
                new_status="COMPROMISED",
                operator_username=reported_by,
                reason=f"Incident {incident.id}: {description}",
            )
            actions.append({
                "action": "KEY_COMPROMISED_SUSPENDED",
                "key_id": affected_key_id,
                "timestamp": datetime.now(UTC).isoformat(),
            })

    incident.actions_taken = actions
    record(
        db,
        actor=reported_by,
        actor_role="admin",
        action="security.incident_raised",
        object_type="security_incident",
        object_id=incident.id,
        details={
            "type": incident_type,
            "severity": severity,
            "affected_key": affected_key_id,
        },
    )
    db.commit()
    db.refresh(incident)
    return incident


def execute_incident_recovery(
    db: Session,
    incident_id: str,
    operator_username: str,
    generate_replacement_key: bool = True,
    resolution_notes: str = "Key compromise contained and replacement key activated.",
) -> dict[str, Any]:
    """Executes recovery workflow: marks incident RESOLVED and issues replacement keys."""
    incident = db.get(SecurityIncident, incident_id)
    if not incident:
        raise ValueError(f"Incident '{incident_id}' not found")

    actions = list(incident.actions_taken or [])
    new_key_id: str | None = None

    if generate_replacement_key and incident.affected_key_id:
        old_key = db.scalars(select(CryptographicKey).where(CryptographicKey.key_id == incident.affected_key_id)).first()
        if old_key:
            # Generate clean replacement key with incremented version
            new_version = old_key.version + 1
            replacement_id = f"{old_key.key_id.rsplit('-v', 1)[0]}-v{new_version}-emergency"
            new_key = kms_service.generate_key(
                db=db,
                key_id=replacement_id,
                algorithm=old_key.algorithm,
                key_purpose=old_key.key_purpose,
                provider_type=old_key.provider_type,
                metadata={"emergency_replacement_for": old_key.key_id, "incident_id": incident.id},
                operator_username=operator_username,
            )
            new_key_id = new_key.key_id
            actions.append({
                "action": "EMERGENCY_REPLACEMENT_KEY_ISSUED",
                "old_key_id": old_key.key_id,
                "new_key_id": new_key_id,
                "timestamp": datetime.now(UTC).isoformat(),
            })

    incident.actions_taken = actions
    incident.status = "RESOLVED"
    incident.resolved_at = datetime.now(UTC)

    record(
        db,
        actor=operator_username,
        actor_role="admin",
        action="security.incident_resolved",
        object_type="security_incident",
        object_id=incident.id,
        details={
            "incident_id": incident.id,
            "actions_count": len(actions),
            "replacement_key": new_key_id,
            "notes": resolution_notes,
        },
    )
    db.commit()

    return {
        "incident_id": incident.id,
        "status": incident.status,
        "resolved_at": incident.resolved_at.isoformat(),
        "replacement_key_id": new_key_id,
        "actions_taken": actions,
    }

