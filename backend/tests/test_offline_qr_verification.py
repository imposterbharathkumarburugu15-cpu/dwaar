"""Tests for Offline Signed QR Verification Engine (Module 4).

Verifies:
1. Valid QR offline verification with issuer public key.
2. Expired credential detection.
3. Invalid signature detection (tampered payload).
4. Unknown issuer key handling.
5. Revocation status handling:
   - REVOCATION_UNAVAILABLE_OFFLINE for normal valid offline credentials.
   - REVOKED_ACCORDING_TO_SYNC_DATA when credential is in synced revocation cache.
6. Honest limitation disclaimers (never claiming live real-time revocation while offline).
"""

import base64
import json
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pramana.offline.qr_verifier import verify_qr_offline
from pramana.verification.signed_qr import sign_payload


@pytest.fixture
def mock_issuer(monkeypatch):
    """Generates an ephemeral issuer keypair and monkeypatches issuer_keys()."""
    priv = Ed25519PrivateKey.generate()
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    pub_b64 = base64.b64encode(pub_bytes).decode("ascii")
    kid = "mock-regulatory-authority-2026"

    mock_db = {
        kid: {
            "name": "State Directorate of Technical Education",
            "public_key": pub_b64,
            "valid_from": "2025-01-01",
            "valid_until": "2027-12-31",
            "status": "active",
        }
    }

    from pramana.verification import signed_qr
    monkeypatch.setattr(signed_qr, "issuer_keys", lambda: mock_db)

    return {"kid": kid, "private_key": priv, "public_key_b64": pub_b64}


def test_valid_offline_qr_verification(mock_issuer):
    """Test 1: Valid signed QR verified offline with explicit revocation notice."""
    payload = {
        "jti": "JTI-CERT-2026-00101",
        "iss": "State DTE",
        "sub": "INST-0001",
        "doc_type": "Land Title Clearance",
        "acres": 5.0,
        "exp": time.time() + 86400 * 365,  # Valid for 1 year
    }
    token = sign_payload(payload, mock_issuer["private_key"], mock_issuer["kid"])

    res = verify_qr_offline(token)

    assert res.status == "SIGNATURE_VALID"
    assert res.signature_valid is True
    assert res.expired is False
    assert res.issuer_known is True
    assert res.revocation_status == "REVOCATION_UNAVAILABLE_OFFLINE"
    assert res.kid == mock_issuer["kid"]
    assert res.payload["acres"] == 5.0
    assert "cannot be verified while offline" in res.offline_revocation_notice


def test_expired_credential_detection(mock_issuer):
    """Test 2: Detects expired credentials and marks as EXPIRED."""
    payload = {
        "jti": "JTI-CERT-EXPIRED",
        "iss": "State DTE",
        "sub": "INST-0001",
        "exp": time.time() - 3600,  # Expired 1 hour ago
    }
    token = sign_payload(payload, mock_issuer["private_key"], mock_issuer["kid"])

    res = verify_qr_offline(token)

    assert res.status == "EXPIRED"
    assert res.signature_valid is True
    assert res.expired is True
    assert "expired" in res.error.lower()


def test_tampered_payload_signature_failure(mock_issuer):
    """Test 3: Modifying payload without valid signature triggers SIGNATURE_INVALID."""
    payload = {
        "jti": "JTI-CERT-GENUINE",
        "acres": 2.5,
    }
    token = sign_payload(payload, mock_issuer["private_key"], mock_issuer["kid"])
    parts = token.split(".")

    # Tamper with payload from 2.5 to 10.0 acres
    tampered_payload = {"jti": "JTI-CERT-GENUINE", "acres": 10.0}
    b64_tampered = base64.urlsafe_b64encode(json.dumps(tampered_payload).encode()).rstrip(b"=").decode()
    tampered_token = f"{parts[0]}.{b64_tampered}.{parts[2]}"

    res = verify_qr_offline(tampered_token)

    assert res.status == "SIGNATURE_INVALID"
    assert res.signature_valid is False
    assert "signature check failed" in res.error.lower()


def test_unknown_issuer_key_detection():
    """Test 4: Token signed by unknown issuer key is reported as ISSUER_UNKNOWN."""
    foreign_priv = Ed25519PrivateKey.generate()
    payload = {"jti": "JTI-FOREIGN-KEY", "data": "test"}
    token = sign_payload(payload, foreign_priv, kid="unknown-authority-999")

    res = verify_qr_offline(token)

    assert res.status == "ISSUER_UNKNOWN"
    assert res.issuer_known is False
    assert "not present in local trust store" in res.error.lower()


def test_revoked_according_to_synced_data(mock_issuer):
    """Test 5: Explicitly flags revoked credentials if present in local sync cache."""
    jti = "JTI-REVOKED-FIRE-NOC-99"
    payload = {
        "jti": jti,
        "iss": "Municipal Fire Authority",
        "sub": "INST-0001",
        "exp": time.time() + 86400,
    }
    token = sign_payload(payload, mock_issuer["private_key"], mock_issuer["kid"])

    revocation_cache = {
        "last_sync_timestamp": "2026-11-01T08:00:00Z",
        "revoked_items": {
            jti: {
                "reason": "Fire safety valve failed inspection",
                "revoked_at": "2026-10-28T14:30:00Z",
            }
        },
    }

    res = verify_qr_offline(token, revocation_cache=revocation_cache)

    assert res.status == "REVOKED_ACCORDING_TO_SYNC_DATA"
    assert res.revocation_status == "REVOKED_ACCORDING_TO_SYNC_DATA"
    assert res.signature_valid is True
    assert "revoked according to last synced data" in res.error.lower()
    assert res.last_sync_timestamp == "2026-11-01T08:00:00Z"
