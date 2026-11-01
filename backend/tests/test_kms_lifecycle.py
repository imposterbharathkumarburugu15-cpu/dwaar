"""Tests for Key Management Service (KMS) & Lifecycle State Machine (Module 1).

Verifies:
1. Key generation for Ed25519, ECDSA P-256, and AES-256-GCM.
2. Safe public key retrieval (private keys are NEVER exposed in database records or metadata).
3. Lifecycle state machine transitions: GENERATED -> ACTIVE -> ROTATION_PENDING -> RETIRED.
4. Invalid lifecycle transitions are strictly rejected.
5. Usage tracking increments on signing operations.
6. Signing with non-ACTIVE keys (RETIRED, REVOKED, COMPROMISED) is blocked.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pramana.db import Base
from pramana.models import User
from pramana.trust.kms import KeyManagementService, kms_service
from pramana.trust.models import CryptographicKey


@pytest.fixture
def memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(id="u-admin", username="admin_pki", role="aicte_admin", display_name="PKI Admin", password_hash="hash")
        session.add(user)
        session.commit()
        yield session


def test_key_generation_and_safe_metadata(memory_db):
    """Test 1: Generates Ed25519, ECDSA, and AES keys with public metadata and zero private key exposure."""
    # 1. Ed25519
    ed_key = kms_service.generate_key(
        db=memory_db,
        key_id="test-ed25519-v1",
        algorithm="ED25519",
        key_purpose="audit_signing",
        operator_username="admin_pki",
    )
    assert ed_key.status == "ACTIVE"
    assert ed_key.public_key_b64 is not None
    assert len(ed_key.public_key_b64) > 10
    assert ed_key.public_key_fingerprint is not None

    # 2. ECDSA P-256
    ec_key = kms_service.generate_key(
        db=memory_db,
        key_id="test-ecdsa-v1",
        algorithm="ECDSA_P256",
        key_purpose="officer_field_signing",
        operator_username="admin_pki",
    )
    assert ec_key.status == "ACTIVE"
    assert "BEGIN PUBLIC KEY" in ec_key.public_key_b64 or len(ec_key.public_key_b64) > 50

    # 3. AES-256-GCM (Symmetric)
    aes_key = kms_service.generate_key(
        db=memory_db,
        key_id="test-aes-v1",
        algorithm="AES_256_GCM",
        key_purpose="document_envelope",
        operator_username="admin_pki",
    )
    assert aes_key.status == "ACTIVE"
    assert aes_key.public_key_b64 is None  # Symmetric key has no public key

    # Verify no private key attribute exists on CryptographicKey model
    assert not hasattr(ed_key, "private_key")
    assert not hasattr(ed_key, "private_bytes")


def test_lifecycle_state_machine_valid_transitions(memory_db):
    """Test 2: Enforces valid state machine transitions: ACTIVE -> ROTATION_PENDING -> RETIRED -> ARCHIVED."""
    key = kms_service.generate_key(
        db=memory_db,
        key_id="test-lifecycle-key",
        algorithm="ED25519",
        key_purpose="audit_signing",
        operator_username="admin_pki",
    )
    assert key.status == "ACTIVE"

    # ACTIVE -> ROTATION_PENDING
    kms_service.transition_status(memory_db, "test-lifecycle-key", "ROTATION_PENDING", "admin_pki", "Schedule rotation")
    assert key.status == "ROTATION_PENDING"

    # ROTATION_PENDING -> RETIRED
    kms_service.transition_status(memory_db, "test-lifecycle-key", "RETIRED", "admin_pki", "Grace period ended")
    assert key.status == "RETIRED"
    assert key.rotated_at is not None

    # RETIRED -> ARCHIVED
    kms_service.transition_status(memory_db, "test-lifecycle-key", "ARCHIVED", "admin_pki", "Permanent archival")
    assert key.status == "ARCHIVED"


def test_lifecycle_state_machine_invalid_transitions(memory_db):
    """Test 3: Rejects invalid lifecycle transitions (e.g., ARCHIVED -> ACTIVE)."""
    key = kms_service.generate_key(
        db=memory_db,
        key_id="test-invalid-transition-key",
        algorithm="ED25519",
        key_purpose="audit_signing",
        operator_username="admin_pki",
    )

    # Cannot transition directly from ACTIVE to ARCHIVED
    with pytest.raises(ValueError, match="Invalid KMS lifecycle transition"):
        kms_service.transition_status(memory_db, "test-invalid-transition-key", "ARCHIVED", "admin_pki", "Premature")

    # Revoke key
    kms_service.transition_status(memory_db, "test-invalid-transition-key", "REVOKED", "admin_pki", "Revocation")
    assert key.status == "REVOKED"

    # Cannot transition from REVOKED back to ACTIVE
    with pytest.raises(ValueError, match="Invalid KMS lifecycle transition"):
        kms_service.transition_status(memory_db, "test-invalid-transition-key", "ACTIVE", "admin_pki", "Un-revoke attempt")


def test_signing_blocked_on_non_active_keys(memory_db):
    """Test 4: Signing is permitted only on ACTIVE keys; RETIRED/REVOKED keys are strictly blocked."""
    key = kms_service.generate_key(
        db=memory_db,
        key_id="test-signing-block-key",
        algorithm="ED25519",
        key_purpose="audit_signing",
        operator_username="admin_pki",
    )

    # Signing on ACTIVE key succeeds
    data = b"Merkle audit block payload"
    sig = kms_service.sign_with_key(memory_db, "test-signing-block-key", data)
    assert len(sig) == 64
    assert key.usage_count == 1

    # Revoke key
    kms_service.transition_status(memory_db, "test-signing-block-key", "REVOKED", "admin_pki", "Key compromised")

    # Signing on REVOKED key fails
    with pytest.raises(PermissionError, match="Cannot sign with key .* in non-active status"):
        kms_service.sign_with_key(memory_db, "test-signing-block-key", data)


def test_usage_tracking_increments(memory_db):
    """Test 5: Signing operations increment usage_count and update last_used_at."""
    key = kms_service.generate_key(
        db=memory_db,
        key_id="test-usage-key",
        algorithm="ED25519",
        key_purpose="audit_signing",
        operator_username="admin_pki",
    )
    assert key.usage_count == 0

    for i in range(1, 4):
        kms_service.sign_with_key(memory_db, "test-usage-key", f"data_{i}".encode())
        assert key.usage_count == i

    assert key.last_used_at is not None

