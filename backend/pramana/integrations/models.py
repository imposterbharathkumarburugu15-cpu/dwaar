"""Database models for Government Integrations, Consent, and External Verification."""

from datetime import UTC, datetime
from typing import Any
import uuid

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


class GovernmentProvider(Base):
    """Registry entry for external government data and verification providers."""

    __tablename__ = "government_providers"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_category: Mapped[str] = mapped_column(String(64), nullable=False)  # API_SETU, DIGILOCKER, PKI, REGULATORY
    integration_type: Mapped[str] = mapped_column(String(64), nullable=False)  # REST_OAUTH2, MTLS, JWS_SIGNING, SIMULATED
    environment: Mapped[str] = mapped_column(String(32), default="sandbox")  # sandbox, staging, production
    connection_status: Mapped[str] = mapped_column(
        String(64), default="NOT_CONFIGURED"
    )  # NOT_CONFIGURED, CONFIGURED, SIMULATED_SANDBOX, REAL_SANDBOX_CONNECTED, AUTHENTICATION_FAILED, SERVICE_UNAVAILABLE, DISABLED
    auth_method: Mapped[str] = mapped_column(String(64), default="API_KEY_OAUTH2")
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    supported_operations: Mapped[list[str]] = mapped_column(JSON, default=list)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    config_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # Non-sensitive config; tokens never saved here
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    verification_requests: Mapped[list["ExternalVerificationRequest"]] = relationship(
        "ExternalVerificationRequest", back_populates="provider", cascade="all, delete-orphan"
    )


class ConsentRecord(Base):
    """Institutional / Applicant purpose-bound consent record for external data verification."""

    __tablename__ = "consent_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"consent_{uuid.uuid4().hex[:12]}")
    application_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    institution_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_id: Mapped[str] = mapped_column(String(64), nullable=False)
    document_category: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")  # ACTIVE, EXPIRED, REVOKED
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audit_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    __table_args__ = (
        Index("ix_consent_app_provider", "application_id", "provider_id"),
    )


class ExternalVerificationRequest(Base):
    """Auditable lifecycle record for outbound government verification invocations."""

    __tablename__ = "external_verification_requests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"evr_{uuid.uuid4().hex[:12]}")
    application_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_id: Mapped[str] = mapped_column(String(64), ForeignKey("government_providers.id"), nullable=False)
    consent_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING")  # PENDING, IN_PROGRESS, COMPLETED, FAILED
    initiated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    request_payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    provider: Mapped["GovernmentProvider"] = relationship("GovernmentProvider", back_populates="verification_requests")
    results: Mapped[list["ExternalVerificationResult"]] = relationship(
        "ExternalVerificationResult", back_populates="verification_request", cascade="all, delete-orphan"
    )


class ExternalVerificationResult(Base):
    """Cryptographically auditable verdict returned from government or issuer verification."""

    __tablename__ = "external_verification_results"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: f"evres_{uuid.uuid4().hex[:12]}")
    verification_id: Mapped[str] = mapped_column(String(64), ForeignKey("external_verification_requests.id"), nullable=False, index=True)
    verdict: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # VERIFIED_BY_AUTHORIZED_ISSUER, CRYPTOGRAPHICALLY_VALID, DOCUMENT_METADATA_VALID, DOCUMENT_MISMATCH, SIGNATURE_INVALID, CERTIFICATE_EXPIRED, ISSUER_UNTRUSTED, AUTHORIZATION_MISSING, VERIFICATION_UNAVAILABLE, MANUAL_REVIEW_REQUIRED
    issuer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    cert_chain_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    signature_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    discrepancies: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    trust_store_version: Mapped[str] = mapped_column(String(64), default="v1.0.0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    verification_request: Mapped["ExternalVerificationRequest"] = relationship(
        "ExternalVerificationRequest", back_populates="results"
    )

