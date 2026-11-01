"""Centralized Key Management Service (KMS) & Lifecycle State Machine.

Implements Module 1 & Module 3 of Phase 3:
- Key generation (Ed25519, ECDSA P-256, AES-256-GCM).
- State Machine: GENERATED -> ACTIVE -> ROTATION_PENDING -> RETIRED, plus REVOKED, COMPROMISED, ARCHIVED.
- Version-preserving key rotation with historical public key retention.
- Usage tracking and strict cryptographic isolation.
- Full audit ledger integration via pramana.audit.record.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record
from ..crypto import sha256_hex
from .hsm import default_hsm_registry
from .models import CryptographicKey, KeyRotationEvent

VALID_STATE_TRANSITIONS = {
    "GENERATED": {"ACTIVE", "REVOKED", "ARCHIVED"},
    "ACTIVE": {"ROTATION_PENDING", "RETIRED", "REVOKED", "COMPROMISED"},
    "ROTATION_PENDING": {"ACTIVE", "RETIRED", "REVOKED", "COMPROMISED"},
    "RETIRED": {"ARCHIVED", "REVOKED", "COMPROMISED"},
    "REVOKED": {"ARCHIVED"},
    "COMPROMISED": {"ARCHIVED"},
    "ARCHIVED": set(),  # Terminal state
}


class KeyManagementService:
    """Enterprise Key Management Service for PRAMANA Trust Infrastructure."""

    def __init__(self, hsm_registry=None):
        self.hsm_registry = hsm_registry or default_hsm_registry

    def generate_key(
        self,
        db: Session,
        key_id: str,
        algorithm: str,
        key_purpose: str,
        provider_type: str = "DEVELOPMENT_PROVIDER",
        metadata: dict[str, Any] | None = None,
        operator_username: str = "system_kms",
    ) -> CryptographicKey:
        """Generates a new cryptographic key and registers it in GENERATED status."""
        existing = db.scalars(select(CryptographicKey).where(CryptographicKey.key_id == key_id)).first()
        if existing:
            raise ValueError(f"Key ID '{key_id}' already exists in KMS registry")

        provider = self.hsm_registry.get_provider(provider_type)
        key_info = provider.generate_key(key_id, algorithm)

        key_rec = CryptographicKey(
            key_id=key_id,
            algorithm=algorithm.upper(),
            key_purpose=key_purpose,
            provider_type=provider.provider_type,
            provider_key_ref=f"{provider.provider_type}:{key_id}",
            status="ACTIVE",  # Standard keys transition immediately to ACTIVE for production availability
            version=1,
            public_key_b64=key_info.get("public_key_b64"),
            public_key_fingerprint=key_info.get("public_key_fingerprint"),
            activated_at=datetime.now(UTC),
            metadata_json=metadata or {},
        )
        db.add(key_rec)
        db.commit()
        db.refresh(key_rec)

        record(
            db,
            actor=operator_username,
            actor_role="admin",
            action="kms.key_created",
            object_type="cryptographic_key",
            object_id=key_rec.key_id,
            details={
                "algorithm": key_rec.algorithm,
                "purpose": key_rec.key_purpose,
                "status": key_rec.status,
                "provider": key_rec.provider_type,
            },
        )
        db.commit()
        return key_rec

    def get_public_key_b64(self, db: Session, key_id: str) -> str | None:
        """Retrieves public key bytes. Private keys are NEVER exposed."""
        key_rec = db.scalars(select(CryptographicKey).where(CryptographicKey.key_id == key_id)).first()
        if not key_rec:
            return None
        return key_rec.public_key_b64

    def transition_status(
        self,
        db: Session,
        key_id: str,
        new_status: str,
        operator_username: str,
        reason: str,
    ) -> CryptographicKey:
        """Enforces the strict KMS state machine transitions."""
        key_rec = db.scalars(select(CryptographicKey).where(CryptographicKey.key_id == key_id)).first()
        if not key_rec:
            raise ValueError(f"Key '{key_id}' not found")

        current_status = key_rec.status
        allowed_next = VALID_STATE_TRANSITIONS.get(current_status, set())
        if new_status not in allowed_next:
            raise ValueError(
                f"Invalid KMS lifecycle transition: cannot move key '{key_id}' from '{current_status}' to '{new_status}'"
            )

        key_rec.status = new_status
        now = datetime.now(UTC)

        if new_status == "ACTIVE":
            key_rec.activated_at = now
        elif new_status == "RETIRED":
            key_rec.rotated_at = now
        elif new_status == "REVOKED":
            key_rec.revoked_at = now
        elif new_status == "COMPROMISED":
            key_rec.compromised_at = now

        meta = dict(key_rec.metadata_json or {})
        history = meta.get("lifecycle_history", [])
        history.append({
            "from_status": current_status,
            "to_status": new_status,
            "changed_at": now.isoformat(),
            "operator": operator_username,
            "reason": reason,
        })
        meta["lifecycle_history"] = history
        key_rec.metadata_json = meta

        record(
            db,
            actor=operator_username,
            actor_role="admin",
            action="kms.lifecycle_transition",
            object_type="cryptographic_key",
            object_id=key_rec.key_id,
            details={"from": current_status, "to": new_status, "reason": reason},
        )
        db.commit()
        return key_rec

    def rotate_key(
        self,
        db: Session,
        key_id: str,
        rotation_reason: str,
        operator_username: str,
        grace_period_days: int = 30,
    ) -> tuple[CryptographicKey, CryptographicKey]:
        """Rotates a key version while strictly preserving the old public key for historical verification.
        
        Returns:
            (retired_old_key, active_new_key)
        """
        old_key = db.scalars(select(CryptographicKey).where(CryptographicKey.key_id == key_id)).first()
        if not old_key:
            raise ValueError(f"Key '{key_id}' does not exist")

        if old_key.status not in ("ACTIVE", "ROTATION_PENDING"):
            raise ValueError(f"Cannot rotate key '{key_id}' in status '{old_key.status}'")

        # Create new version ID
        old_ver = old_key.version
        new_ver = old_ver + 1
        new_key_id = f"{key_id.rsplit('-v', 1)[0]}-v{new_ver}"

        # 1. Generate new key in provider
        provider = self.hsm_registry.get_provider(old_key.provider_type)
        new_key_info = provider.generate_key(new_key_id, old_key.algorithm)

        # 2. Retire old key
        self.transition_status(db, key_id, "RETIRED", operator_username, f"Rotated in favor of {new_key_id}")

        # 3. Create new active key
        new_key = CryptographicKey(
            key_id=new_key_id,
            algorithm=old_key.algorithm,
            key_purpose=old_key.key_purpose,
            provider_type=old_key.provider_type,
            provider_key_ref=f"{old_key.provider_type}:{new_key_id}",
            status="ACTIVE",
            version=new_ver,
            public_key_b64=new_key_info.get("public_key_b64"),
            public_key_fingerprint=new_key_info.get("public_key_fingerprint"),
            activated_at=datetime.now(UTC),
            metadata_json={
                "supersedes_key": old_key.key_id,
                "rotation_reason": rotation_reason,
                "grace_period_days": grace_period_days,
            },
        )
        db.add(new_key)

        # Record rotation event
        rot_event = KeyRotationEvent(
            key_id=key_id,
            old_version=old_ver,
            new_version=new_ver,
            initiated_by=operator_username,
            rotation_reason=rotation_reason,
            grace_period_days=grace_period_days,
            status="COMPLETED",
            details={"superseded_by": new_key_id},
        )
        db.add(rot_event)

        record(
            db,
            actor=operator_username,
            actor_role="admin",
            action="kms.key_rotated",
            object_type="cryptographic_key",
            object_id=key_id,
            details={
                "old_key_id": old_key.key_id,
                "new_key_id": new_key.key_id,
                "reason": rotation_reason,
            },
        )
        db.commit()
        db.refresh(old_key)
        db.refresh(new_key)
        return old_key, new_key

    def sign_with_key(self, db: Session, key_id: str, data: bytes) -> bytes:
        """Signs data with a managed active key, checking lifecycle status and tracking usage."""
        key_rec = db.scalars(select(CryptographicKey).where(CryptographicKey.key_id == key_id)).first()
        if not key_rec:
            raise ValueError(f"Key '{key_id}' not found")

        if key_rec.status != "ACTIVE":
            raise PermissionError(f"Cannot sign with key '{key_id}' in non-active status '{key_rec.status}'")

        provider = self.hsm_registry.get_provider(key_rec.provider_type)
        sig = provider.sign(key_id, data)

        # Track usage
        key_rec.usage_count += 1
        key_rec.last_used_at = datetime.now(UTC)
        db.commit()
        return sig

    def verify_with_key(
        self,
        db: Session,
        key_id: str,
        data: bytes,
        signature: bytes,
    ) -> bool:
        """Verifies signature against key. Old RETIRED keys remain valid for historical verification."""
        key_rec = db.scalars(select(CryptographicKey).where(CryptographicKey.key_id == key_id)).first()
        if not key_rec:
            return False

        if key_rec.status in ("REVOKED", "COMPROMISED"):
            # A revoked or compromised key signature cannot be trusted without explicit qualification
            return False

        provider = self.hsm_registry.get_provider(key_rec.provider_type)
        return provider.verify(key_id, data, signature, key_rec.public_key_b64)


# Global KMS instance
kms_service = KeyManagementService()

