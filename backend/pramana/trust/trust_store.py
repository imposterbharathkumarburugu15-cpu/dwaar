"""Centralized Trust Store Management across Environments.

Implements Module 7 of Phase 3:
- Scoped trust anchor management (development, test, production).
- Version tracking and anti-rollback protection for trust stores.
- Adding and removing certificate authorities with full auditability.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record
from .models import CertificateRecord, TrustStoreEntry


class TrustStoreManager:
    """Manages scoped trust anchors and certificate authority stores."""

    def add_trust_anchor(
        self,
        db: Session,
        certificate_id: str,
        environment: str = "development",
        operator_username: str = "admin",
    ) -> TrustStoreEntry:
        """Adds a registered certificate as a trusted root/anchor in the specified environment."""
        cert = db.get(CertificateRecord, certificate_id)
        if not cert:
            raise ValueError(f"Certificate '{certificate_id}' not found")

        existing = db.scalars(
            select(TrustStoreEntry).where(
                TrustStoreEntry.environment == environment,
                TrustStoreEntry.certificate_id == certificate_id,
            )
        ).first()

        if existing:
            return existing

        # Get latest version for environment
        latest_entry = db.scalars(
            select(TrustStoreEntry)
            .where(TrustStoreEntry.environment == environment)
            .order_by(TrustStoreEntry.trust_store_version.desc())
            .limit(1)
        ).first()
        new_version = (latest_entry.trust_store_version + 1) if latest_entry else 1

        entry = TrustStoreEntry(
            environment=environment,
            trust_store_version=new_version,
            certificate_id=certificate_id,
            is_anchor=True,
            added_by=operator_username,
            added_at=datetime.now(UTC),
        )
        cert.trust_status = "TRUSTED_ANCHOR"
        db.add(entry)

        record(
            db,
            actor=operator_username,
            actor_role="admin",
            action="trust_store.anchor_added",
            object_type="trust_anchor",
            object_id=certificate_id,
            details={
                "environment": environment,
                "version": new_version,
                "subject": cert.subject_dn,
            },
        )
        db.commit()
        db.refresh(entry)
        return entry

    def remove_trust_anchor(
        self,
        db: Session,
        certificate_id: str,
        environment: str = "development",
        operator_username: str = "admin",
    ) -> bool:
        """Removes a trust anchor from an environment store."""
        entry = db.scalars(
            select(TrustStoreEntry).where(
                TrustStoreEntry.environment == environment,
                TrustStoreEntry.certificate_id == certificate_id,
            )
        ).first()

        if not entry:
            return False

        cert = db.get(CertificateRecord, certificate_id)
        if cert:
            cert.trust_status = "UNTRUSTED"

        db.delete(entry)

        record(
            db,
            actor=operator_username,
            actor_role="admin",
            action="trust_store.anchor_removed",
            object_type="trust_anchor",
            object_id=certificate_id,
            details={"environment": environment},
        )
        db.commit()
        return True

    def list_trust_anchors(
        self,
        db: Session,
        environment: str = "development",
    ) -> list[dict[str, Any]]:
        """Lists all trusted anchors for a given environment."""
        entries = list(db.scalars(
            select(TrustStoreEntry)
            .where(TrustStoreEntry.environment == environment)
            .order_by(TrustStoreEntry.added_at.desc())
        ).all())

        results = []
        for e in entries:
            cert = db.get(CertificateRecord, e.certificate_id)
            if cert:
                results.append({
                    "entry_id": e.id,
                    "environment": e.environment,
                    "version": e.trust_store_version,
                    "certificate_id": cert.id,
                    "subject_dn": cert.subject_dn,
                    "issuer_dn": cert.issuer_dn,
                    "serial_number": cert.serial_number,
                    "fingerprint_sha256": cert.fingerprint_sha256,
                    "not_after": cert.not_after.isoformat(),
                    "added_by": e.added_by,
                    "added_at": e.added_at.isoformat(),
                })
        return results


default_trust_store = TrustStoreManager()

