"""Database models for PRAMANA Hardware Security and Trust Infrastructure (Phase 3).

Registered by pramana.db.init_db.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from ..models import UTCDateTime, new_id, utcnow


class CryptographicKey(Base):
    """A cryptographic key managed by the Key Management Service (KMS)."""

    __tablename__ = "cryptographic_keys"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("kms"))
    key_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    algorithm: Mapped[str] = mapped_column(String(30), index=True)  # Ed25519, ECDSA_P256, AES_256_GCM
    key_purpose: Mapped[str] = mapped_column(String(40), index=True)  # audit_signing, document_envelope, officer_field_signing, qr_issuance
    provider_type: Mapped[str] = mapped_column(String(40), default="DEVELOPMENT_PROVIDER", index=True)
    provider_key_ref: Mapped[str] = mapped_column(String(120))

    # Lifecycle State Machine:
    # GENERATED -> ACTIVE -> ROTATION_PENDING -> RETIRED
    # Additional: REVOKED, COMPROMISED, ARCHIVED
    status: Mapped[str] = mapped_column(String(30), default="GENERATED", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    # Public metadata (safe for client inspection)
    public_key_b64: Mapped[str | None] = mapped_column(Text)
    public_key_fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)

    # Lifecycle timestamps
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    activated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    rotated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    compromised_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    # Metadata & Tracking
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class KeyRotationEvent(Base):
    """Historical record of key rotation transactions."""

    __tablename__ = "key_rotation_events"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("rot"))
    key_id: Mapped[str] = mapped_column(String(80), index=True)
    old_version: Mapped[int] = mapped_column(Integer)
    new_version: Mapped[int] = mapped_column(Integer)
    initiated_by: Mapped[str] = mapped_column(String(80))
    rotation_reason: Mapped[str] = mapped_column(String(120))
    grace_period_days: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[str] = mapped_column(String(30), default="COMPLETED")  # COMPLETED, FAILED, PENDING_APPROVAL
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class CertificateRecord(Base):
    """Managed X.509 Certificate and Trust Anchor records."""

    __tablename__ = "certificate_records"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("crt"))
    serial_number: Mapped[str] = mapped_column(String(80), index=True)
    issuer_dn: Mapped[str] = mapped_column(String(255), index=True)
    subject_dn: Mapped[str] = mapped_column(String(255), index=True)
    fingerprint_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    not_before: Mapped[datetime] = mapped_column(UTCDateTime())
    not_after: Mapped[datetime] = mapped_column(UTCDateTime())
    certificate_pem: Mapped[str] = mapped_column(Text)

    # Status: TRUSTED_ANCHOR, INTERMEDIATE_CA, END_ENTITY, UNTRUSTED
    trust_status: Mapped[str] = mapped_column(String(30), default="UNTRUSTED", index=True)
    # Revocation: GOOD, REVOKED, UNKNOWN
    revocation_status: Mapped[str] = mapped_column(String(40), default="UNKNOWN", index=True)

    crl_distribution_points: Mapped[list[str]] = mapped_column(JSON, default=list)
    ocsp_responder_urls: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class CRLRecord(Base):
    """Certificate Revocation List (CRL) synchronization records."""

    __tablename__ = "crl_records"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("crl"))
    issuer_dn: Mapped[str] = mapped_column(String(255), index=True)
    crl_number: Mapped[int] = mapped_column(Integer, index=True)
    this_update: Mapped[datetime] = mapped_column(UTCDateTime())
    next_update: Mapped[datetime] = mapped_column(UTCDateTime())
    revoked_serials_count: Mapped[int] = mapped_column(Integer, default=0)
    revoked_serials_list: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    signature_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    # Status: GOOD_AS_OF_LAST_SYNC, CRL_EXPIRED, CRL_UNAVAILABLE, ROLLBACK_ATTEMPT
    status: Mapped[str] = mapped_column(String(30), default="GOOD_AS_OF_LAST_SYNC", index=True)
    raw_crl_bytes: Mapped[bytes | None] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class TrustStoreEntry(Base):
    """Scoped Trust Store entry (development, test, production)."""

    __tablename__ = "trust_store_entries"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("tse"))
    environment: Mapped[str] = mapped_column(String(30), index=True)  # development, test, production
    trust_store_version: Mapped[int] = mapped_column(Integer, default=1)
    certificate_id: Mapped[str] = mapped_column(ForeignKey("certificate_records.id"), index=True)
    is_anchor: Mapped[bool] = mapped_column(Boolean, default=True)
    added_by: Mapped[str] = mapped_column(String(80))
    added_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


class SecurityIncident(Base):
    """Cryptographic incident and key compromise response record."""

    __tablename__ = "security_incidents"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: new_id("inc"))
    incident_type: Mapped[str] = mapped_column(String(60), index=True)  # KEY_COMPROMISE, SUSPICIOUS_SIGNING, TRUST_STORE_CORRUPTION
    affected_key_id: Mapped[str | None] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="HIGH", index=True)  # CRITICAL, HIGH, MEDIUM
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="OPEN", index=True)  # OPEN, INVESTIGATING, CONTAINED, RESOLVED
    actions_taken: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    reported_by: Mapped[str] = mapped_column(String(80))
    reported_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

