"""Tests for Key Rotation Engine & Historical Signature Retention (Module 3).

Verifies:
1. Versioned key rotation (v1 -> v2) creating a new ACTIVE key while preserving old key metadata.
2. Historical verification guarantee: signatures signed with v1 key remain 100% verifiable using retained v1 public key.
3. New signatures are produced using active v2 key.
4. Old key status transitions to RETIRED.
5. Key rotation events are logged into the audit ledger.
6. Rejection of rotation on non-active or revoked keys.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pramana.db import Base
from pramana.models import User
from pramana.trust.kms import kms_service
from pramana.trust.models import CryptographicKey, KeyRotationEvent


@pytest.fixture
def memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(id="u-admin", username="admin_rot", role="aicte_admin", display_name="Rotation Admin", password_hash="hash")
        session.add(user)
        session.commit()
        yield session


def test_key_rotation_and_historical_verification(memory_db):
    """Test 1: Historical signatures signed with v1 key remain verifiable after rotation to v2."""
    # 1. Generate v1 key
    v1_key = kms_service.generate_key(
        db=memory_db,
        key_id="prm-audit-signing-v1",
        algorithm="ED25519",
        key_purpose="audit_signing",
        operator_username="admin_rot",
    )
    assert v1_key.version == 1
    assert v1_key.status == "ACTIVE"

    # 2. Sign document with v1 key
    historical_doc = b"Historical Regulatory Audit Block #100 - Dated 2025-10-15"
    historical_sig = kms_service.sign_with_key(memory_db, "prm-audit-signing-v1", historical_doc)
    assert len(historical_sig) == 64

    # Verify signature before rotation
    assert kms_service.verify_with_key(memory_db, "prm-audit-signing-v1", historical_doc, historical_sig) is True

    # 3. Rotate key to v2
    old_key, new_key = kms_service.rotate_key(
        db=memory_db,
        key_id="prm-audit-signing-v1",
        rotation_reason="Annual cryptographic hygiene rotation",
        operator_username="admin_rot",
    )

    assert old_key.status == "RETIRED"
    assert new_key.key_id == "prm-audit-signing-v2"
    assert new_key.version == 2
    assert new_key.status == "ACTIVE"

    # 4. HISTORICAL VERIFICATION: Old signature remains completely verifiable using retained v1 key!
    assert kms_service.verify_with_key(memory_db, "prm-audit-signing-v1", historical_doc, historical_sig) is True

    # 5. NEW SIGNING: Sign new document with v2 key
    new_doc = b"New Regulatory Audit Block #200 - Dated 2026-11-01"
    new_sig = kms_service.sign_with_key(memory_db, "prm-audit-signing-v2", new_doc)
    assert len(new_sig) == 64
    assert kms_service.verify_with_key(memory_db, "prm-audit-signing-v2", new_doc, new_sig) is True

    # 6. Cannot sign new document with old RETIRED v1 key
    with pytest.raises(PermissionError, match="Cannot sign with key .* in non-active status"):
        kms_service.sign_with_key(memory_db, "prm-audit-signing-v1", new_doc)


def test_rotation_event_audit_record(memory_db):
    """Test 2: Key rotation transaction creates a detailed KeyRotationEvent record."""
    kms_service.generate_key(
        db=memory_db,
        key_id="prm-qr-issuance-v1",
        algorithm="ED25519",
        key_purpose="qr_issuance",
        operator_username="admin_rot",
    )

    old_k, new_k = kms_service.rotate_key(
        db=memory_db,
        key_id="prm-qr-issuance-v1",
        rotation_reason="Scheduled bi-annual rotation",
        operator_username="admin_rot",
        grace_period_days=45,
    )

    # Inspect rotation event record
    event = memory_db.query(KeyRotationEvent).filter_by(key_id="prm-qr-issuance-v1").first()
    assert event is not None
    assert event.old_version == 1
    assert event.new_version == 2
    assert event.initiated_by == "admin_rot"
    assert event.grace_period_days == 45
    assert event.status == "COMPLETED"


def test_cannot_rotate_revoked_or_invalid_key(memory_db):
    """Test 3: Attempting to rotate a REVOKED or non-existent key is rejected."""
    key = kms_service.generate_key(
        db=memory_db,
        key_id="prm-revoked-key-v1",
        algorithm="ED25519",
        key_purpose="audit_signing",
        operator_username="admin_rot",
    )
    kms_service.transition_status(memory_db, "prm-revoked-key-v1", "REVOKED", "admin_rot", "Revoked")

    with pytest.raises(ValueError, match="Cannot rotate key .* in status 'REVOKED'"):
        kms_service.rotate_key(memory_db, "prm-revoked-key-v1", "Invalid attempt", "admin_rot")

    with pytest.raises(ValueError, match="does not exist"):
        kms_service.rotate_key(memory_db, "nonexistent-key-v1", "Invalid attempt", "admin_rot")

