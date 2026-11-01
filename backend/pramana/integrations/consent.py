"""Purpose-Bound Consent and Authorization Management for Government Data Access."""

from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from ..audit import record
from .models import ConsentRecord

logger = logging.getLogger("pramana.integrations.consent")


class ConsentExpiredError(ValueError):
    """Raised when consent validity window has elapsed."""
    pass


class ConsentRevokedError(ValueError):
    """Raised when consent was explicitly revoked."""
    pass


class ConsentService:
    """Manages applicant and institutional consent records with audit preservation."""

    def grant_consent(
        self,
        db: Session,
        application_id: str,
        institution_id: str,
        provider_id: str,
        document_category: str,
        purpose: str,
        validity_days: int = 90,
        operator: str = "institution_admin",
    ) -> ConsentRecord:
        """Grants purpose-bound consent for accessing external registry records."""
        valid_until = datetime.now(UTC) + timedelta(days=validity_days)

        consent = ConsentRecord(
            application_id=application_id,
            institution_id=institution_id,
            provider_id=provider_id,
            document_category=document_category,
            purpose=purpose,
            status="ACTIVE",
            valid_until=valid_until,
            created_at=datetime.now(UTC),
        )
        db.add(consent)
        db.commit()
        db.refresh(consent)

        audit_entry = record(
            db,
            actor=operator,
            actor_role="institution_admin",
            action="consent.granted",
            object_type="consent_record",
            object_id=consent.id,
            details={
                "application_id": application_id,
                "provider_id": provider_id,
                "category": document_category,
                "purpose": purpose,
                "valid_until": valid_until.isoformat(),
            },
        )
        consent.audit_event_id = str(audit_entry.seq)
        db.commit()
        return consent

    def verify_active_consent(
        self,
        db: Session,
        application_id: str,
        provider_id: str,
        document_category: str,
    ) -> ConsentRecord:
        """Validates that a valid, unexpired, unrevoked consent exists for the operation."""
        consent = db.scalars(
            select(ConsentRecord).where(
                and_(
                    ConsentRecord.application_id == application_id,
                    ConsentRecord.provider_id == provider_id,
                    ConsentRecord.document_category == document_category,
                    ConsentRecord.status == "ACTIVE",
                )
            ).order_by(ConsentRecord.created_at.desc())
        ).first()

        if not consent:
            raise KeyError(
                f"No active consent found for application '{application_id}', provider '{provider_id}', category '{document_category}'"
            )

        now = datetime.now(UTC)
        if consent.valid_until.tzinfo is None:
            now_cmp = datetime.now(UTC).replace(tzinfo=None)
        else:
            now_cmp = now

        if consent.valid_until < now_cmp:
            consent.status = "EXPIRED"
            db.commit()
            raise ConsentExpiredError(f"Consent '{consent.id}' expired on {consent.valid_until.isoformat()}")

        return consent

    def revoke_consent(
        self,
        db: Session,
        consent_id: str,
        revoked_by: str,
        reason: str | None = None,
    ) -> ConsentRecord:
        """Revokes an active consent record immediately."""
        consent = db.get(ConsentRecord, consent_id)
        if not consent:
            raise KeyError(f"Consent '{consent_id}' not found")

        consent.status = "REVOKED"
        consent.revoked_at = datetime.now(UTC)
        consent.revoked_by = revoked_by
        db.commit()

        record(
            db,
            actor=revoked_by,
            actor_role="institution_admin",
            action="consent.revoked",
            object_type="consent_record",
            object_id=consent_id,
            details={"application_id": consent.application_id, "reason": reason},
        )
        return consent


default_consent_service = ConsentService()
