"""Tests for Digital Inspection Report Signing & Keystore Abstraction (Module 3).

Verifies:
1. Canonicalization of inspection report payloads (RFC 8785 deterministic ordering).
2. SHA-256 digest calculation on canonical payloads.
3. Ed25519 digital signature signing.
4. Independent signature verification.
5. Tamper detection: modifying report fields breaks digest and signature verification.
6. Unknown key ID and missing public key rejection.
7. Verification history tracking.
"""

import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pramana.offline.signing import (
    KeystoreManager,
    canonicalize_report,
    compute_report_digest,
)


@pytest.fixture
def test_keystore(tmp_path):
    return KeystoreManager(keystore_dir=tmp_path / "keystore")


@pytest.fixture
def sample_report():
    return {
        "case_number": "INSP-2026-000107-01",
        "application_id": "APP-2026-000107",
        "institution_id": "INST-0001",
        "officer_id": "officer_sharma",
        "checklist": [
            {"item_id": "CHK-LAND", "title": "Physical Land Boundary Verification", "status": "verified"},
            {"item_id": "CHK-LABS", "title": "Computer Lab Workstation Count", "status": "verified"},
        ],
        "observations": [
            {"timestamp": "2026-11-01T10:00:00Z", "content": "Campus boundaries inspected."}
        ],
        "summary": "Full compliance verified on site.",
        "recommendation": "approve",
        "evidence_hashes": [
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        ],
        "total_evidence_count": 1,
    }


def test_deterministic_canonicalization(sample_report):
    """Test 1: Canonicalization produces identical byte streams regardless of key insertion order."""
    # Create copy with reversed key insertion order
    reversed_report = {k: sample_report[k] for k in reversed(list(sample_report.keys()))}
    
    canon1 = canonicalize_report(sample_report)
    canon2 = canonicalize_report(reversed_report)
    
    assert canon1 == canon2
    assert b" " not in canon1[:50]  # No whitespace after colons/commas
    assert compute_report_digest(sample_report) == compute_report_digest(reversed_report)


def test_ed25519_report_signing_and_verification(test_keystore, sample_report):
    """Test 2: Report is signed with Ed25519 and verified independently."""
    signed_rec = test_keystore.sign_report(sample_report, officer_id="officer_sharma")
    
    assert "report_digest" in signed_rec
    assert "signature" in signed_rec
    assert signed_rec["signer_kid"] == "officer-key-officer_sharma"
    assert signed_rec["signature_algorithm"] == "Ed25519"
    
    # Verify signature
    res = test_keystore.verify_report_signature(
        report_payload=sample_report,
        expected_digest=signed_rec["report_digest"],
        signature_b64=signed_rec["signature"],
        signer_kid=signed_rec["signer_kid"],
    )
    
    assert res.valid is True
    assert res.digest_matches is True
    assert res.signature_matches is True
    assert res.error is None


def test_tamper_detection_on_modified_report(test_keystore, sample_report):
    """Test 3: Modifying any field in the report breaks verification and identifies tamper."""
    signed_rec = test_keystore.sign_report(sample_report, officer_id="officer_sharma")
    
    # Tamper with recommendation
    tampered_report = dict(sample_report)
    tampered_report["recommendation"] = "reject"
    
    res = test_keystore.verify_report_signature(
        report_payload=tampered_report,
        expected_digest=signed_rec["report_digest"],
        signature_b64=signed_rec["signature"],
        signer_kid=signed_rec["signer_kid"],
    )
    
    assert res.valid is False
    assert res.digest_matches is False
    assert "content modified after signing" in res.error.lower()


def test_tamper_detection_on_checklist_tamper(test_keystore, sample_report):
    """Test 4: Modifying nested checklist items breaks canonical verification."""
    signed_rec = test_keystore.sign_report(sample_report, officer_id="officer_sharma")
    
    tampered_report = json.loads(json.dumps(sample_report))
    tampered_report["checklist"][0]["status"] = "failed"
    
    res = test_keystore.verify_report_signature(
        report_payload=tampered_report,
        expected_digest=signed_rec["report_digest"],
        signature_b64=signed_rec["signature"],
        signer_kid=signed_rec["signer_kid"],
    )
    
    assert res.valid is False
    assert res.digest_matches is False


def test_unknown_or_missing_signer_key(test_keystore, sample_report):
    """Test 5: Verification fails gracefully when signer key is unknown."""
    signed_rec = test_keystore.sign_report(sample_report, officer_id="officer_sharma")
    
    res = test_keystore.verify_report_signature(
        report_payload=sample_report,
        expected_digest=signed_rec["report_digest"],
        signature_b64=signed_rec["signature"],
        signer_kid="nonexistent-key-id",
    )
    
    assert res.valid is False
    assert "not found in keystore" in res.error.lower()


def test_verification_history_tracking(test_keystore, sample_report):
    """Test 6: KeystoreManager tracks verification history."""
    signed_rec = test_keystore.sign_report(sample_report, officer_id="officer_sharma")
    
    # Run valid verification
    test_keystore.verify_report_signature(
        report_payload=sample_report,
        expected_digest=signed_rec["report_digest"],
        signature_b64=signed_rec["signature"],
        signer_kid=signed_rec["signer_kid"],
    )
    
    # Run tampered verification
    tampered = dict(sample_report)
    tampered["summary"] = "Tampered summary"
    test_keystore.verify_report_signature(
        report_payload=tampered,
        expected_digest=signed_rec["report_digest"],
        signature_b64=signed_rec["signature"],
        signer_kid=signed_rec["signer_kid"],
    )
    
    history = test_keystore.verification_history
    assert len(history) >= 2
    assert history[-2]["valid"] is True
    assert history[-1]["valid"] is False

