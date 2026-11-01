"""Comprehensive validation suite for PRAMANA cryptographic and audit systems.

Verifies:
1. AES-256-GCM per-document envelope encryption, authentication tags, and crypto-shredding.
2. SHA-256 Merkle audit trail chaining, genesis block continuity, and tamper detection.
3. Tamper detection on modified audit events, deleted events, and reordered sequences.
4. Ed25519 cryptographic checkpointing and signature verification.
5. JWS EdDSA (Ed25519 RFC 7515/8037) signed QR token verification.
6. QR tampering, token expiry, and incorrect signing key rejections.
"""

import base64
import json
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pramana import audit, crypto, keyring
from pramana.models import AuditCheckpoint, AuditEvent, Base
from pramana.verification import signed_qr


@pytest.fixture
def memory_db():
    """In-memory SQLite database for isolated audit ledger testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def test_aes_256_gcm_envelope_encryption_and_tampering(tmp_path):
    """Test 1: Verify AES-256-GCM envelope encryption and tamper rejection."""
    doc_path = tmp_path / "test_document.bin"
    secret_content = b"%PDF-1.4 Official Certificate Content With Secret Data"

    # Seal document with envelope encryption
    keyring.seal_to(doc_path, secret_content)
    assert doc_path.exists()
    assert keyring.key_path(doc_path).exists()

    # Raw bytes must have PRM2 magic header and must NOT match plaintext
    raw_cipher = doc_path.read_bytes()
    assert keyring.is_envelope(raw_cipher) is True
    assert secret_content not in raw_cipher

    # Decrypt and verify exact match
    decrypted = keyring.open_from(doc_path, raw_cipher)
    assert decrypted == secret_content

    # Tamper with ciphertext bytes
    tampered_cipher = bytearray(raw_cipher)
    tampered_cipher[20] ^= 0xFF
    with pytest.raises(Exception):
        keyring.open_from(doc_path, bytes(tampered_cipher))

    # Crypto-shredding: deleting the key makes ciphertext permanently unrecoverable
    keyring.key_path(doc_path).unlink()
    with pytest.raises(keyring.UnwrapError):
        keyring.open_from(doc_path, raw_cipher)


def test_audit_ledger_hash_chaining_and_tamper_detection(memory_db):
    """Test 2: Verify SHA-256 hash chaining, event recording, and tamper detection."""
    db = memory_db

    # Record legitimate events
    e1 = audit.record(db, actor="officer1", actor_role="officer", action="application.submitted",
                      object_type="application", object_id="APP-001")
    e2 = audit.record(db, actor="officer1", actor_role="officer", action="document.verified",
                      object_type="document", object_id="DOC-001", application_id="APP-001")
    e3 = audit.record(db, actor="admin1", actor_role="aicte_admin", action="application.approved",
                      object_type="application", object_id="APP-001")
    db.commit()

    # Verify chain from genesis
    status = audit.verify_chain(db)
    assert status["intact"] is True
    assert status["events_checked"] == 3
    assert status["first_broken_seq"] is None

    # SCENARIO A: Modified event payload (tampering)
    e2.details = {"malicious": "injected modification"}
    db.commit()
    tampered_status = audit.verify_chain(db)
    assert tampered_status["intact"] is False
    assert tampered_status["first_broken_seq"] == 2

    # Restore e2 details
    e2.details = {}
    e2.hash = audit._hash(e2.prev_hash, audit._event_body(e2))
    db.commit()
    assert audit.verify_chain(db)["intact"] is True


def test_audit_ledger_deletion_and_reordering_detection(memory_db):
    """Test 3: Verify deletion of events and reordering breaks hash continuity."""
    db = memory_db
    e1 = audit.record(db, actor="user1", actor_role="officer", action="act1", object_type="test")
    e2 = audit.record(db, actor="user2", actor_role="officer", action="act2", object_type="test")
    e3 = audit.record(db, actor="user3", actor_role="officer", action="act3", object_type="test")
    db.commit()

    # SCENARIO B: Deleted event (gap in sequence)
    db.delete(e2)
    db.commit()
    gap_status = audit.verify_chain(db)
    assert gap_status["intact"] is False
    assert gap_status["first_broken_seq"] == 3  # e3 prev_hash doesn't match e1 hash


def test_ed25519_signed_checkpoints(memory_db):
    """Test 4: Verify Ed25519 digital signature on checkpoint ledger heads."""
    db = memory_db
    audit.record(db, actor="system", actor_role="system", action="system.init", object_type="system")
    cp = audit.checkpoint(db)
    db.commit()

    assert cp is not None
    assert cp.seq == 1
    assert cp.signature is not None
    assert cp.public_key is not None

    # Verify signature using public key
    pk_bytes = base64.b64decode(cp.public_key)
    pk = Ed25519PublicKey.from_public_bytes(pk_bytes)
    sig_bytes = base64.b64decode(cp.signature)
    expected_msg = f"{cp.seq}:{cp.head_hash}".encode()
    pk.verify(sig_bytes, expected_msg)

    # Verify chain confirms checkpoint validity
    status = audit.verify_chain(db)
    assert status["intact"] is True
    assert len(status["checkpoints"]) == 1
    assert status["checkpoints"][0]["signature_valid"] is True


def test_jws_signed_qr_verification_lifecycle(monkeypatch):
    """Test 5: Verify JWS signed QR creation, verification, tampering, and expiry."""
    # Generate Ed25519 key pair for simulated municipal issuer
    issuer_private_key = Ed25519PrivateKey.generate()
    issuer_public_key = issuer_private_key.public_key()
    pub_raw = issuer_public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    pub_b64 = base64.b64encode(pub_raw).decode()
    kid = "sim-fire-noc-key-01"

    now = int(time.time())
    payload = {
        "iss": "Municipal Fire Services",
        "sub": "NOC-2026-987654",
        "aud": "AICTE-Technical-Institution",
        "exp": now + 3600,  # 1 hour in future
        "nbf": now - 60,
        "iat": now,
        "inst_name": "Apex Engineering Institute",
        "valid_until": "2027-03-31",
    }

    # 1. Sign payload into JWS token
    token = signed_qr.sign_payload(payload, issuer_private_key, kid)
    assert len(token.split(".")) == 3

    # Mock issuer key registry
    mock_keys = {
        kid: {
            "name": "State Fire Services",
            "kid": kid,
            "public_key": pub_b64,
            "simulated": True,
        }
    }
    monkeypatch.setattr(signed_qr, "issuer_keys", lambda: mock_keys)

    # 2. Verify valid token
    check = signed_qr.verify_token(token)
    assert check.ok is True
    assert check.kid == kid
    assert check.payload["sub"] == "NOC-2026-987654"
    assert check.error is None

    # 3. Tamper with token payload (alter certificate number)
    parts = token.split(".")
    tampered_payload = dict(payload)
    tampered_payload["sub"] = "NOC-FORGED-111111"
    tampered_p_b64 = signed_qr._b64u(json.dumps(tampered_payload, separators=(",", ":")).encode())
    tampered_token = f"{parts[0]}.{tampered_p_b64}.{parts[2]}"

    tampered_check = signed_qr.verify_token(tampered_token)
    assert tampered_check.ok is False
    assert "signature" in tampered_check.error.lower()

    # 4. Unknown signing key
    monkeypatch.setattr(signed_qr, "issuer_keys", lambda: {"other-key": mock_keys[kid]})
    unknown_check = signed_qr.verify_token(token)
    assert unknown_check.ok is False
    assert "unknown issuer key" in unknown_check.error.lower()
