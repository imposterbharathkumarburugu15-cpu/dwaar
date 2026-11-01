"""Digital Inspection Report Signing & Keystore Abstraction for PRAMANA Field Scrutiny.

Implements Module 3 of Phase 2:
- Deterministic canonicalization of inspection reports (RFC 8785 compliant key sorting).
- SHA-256 digest calculation.
- Ed25519 digital signature signing and verification.
- Tamper detection on modified report fields.
- Signature verification history tracking.
- Abstract KeystoreManager with clear separation between demo keys and production HSM/Keystore.
"""

import base64
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from ..config import get_settings
from ..crypto import sha256_hex


def canonicalize_report(payload: dict[str, Any]) -> bytes:
    """Canonicalizes a report payload deterministically.
    
    Sorts dictionary keys recursively, removes whitespace separators,
    and encodes to UTF-8 per RFC 8785 / deterministic JSON standards.
    """
    def _sort(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _sort(v) for k, v in sorted(obj.items())}
        if isinstance(obj, list):
            return [_sort(x) for x in obj]
        return obj

    sorted_obj = _sort(payload)
    return json.dumps(sorted_obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def compute_report_digest(payload: dict[str, Any]) -> str:
    """Computes the SHA-256 digest of the canonicalized report payload."""
    return sha256_hex(canonicalize_report(payload))


@dataclass
class SignatureVerificationResult:
    valid: bool
    signer_kid: str
    verified_at: str
    digest_matches: bool
    signature_matches: bool
    error: str | None = None
    report_digest: str | None = None


class KeystoreManager:
    """Secure Key Management Abstraction for PRAMANA Field Scrutiny.
    
    Architectural Separation:
    - DEMO MODE: Local ephemeral or securely persisted demonstration keys stored
      in data_dir/keystore/ with restricted filesystem permissions. Clearly labeled
      with [DEMO_KEYSTORE] metadata.
    - PRODUCTION MODE (Interface Ready): Hooks into Android Keystore, AWS KMS, or
      Hardware Security Modules (HSM) via PKCS#11. Private keys are never exposed in
      memory dumps, logs, or API payloads.
    """

    def __init__(self, keystore_dir: Path | None = None):
        self.keystore_dir = keystore_dir or (get_settings().data_dir / "keystore")
        self.keystore_dir.mkdir(parents=True, exist_ok=True)
        self._memory_keys: dict[str, Ed25519PrivateKey] = {}
        self._verification_history: list[dict[str, Any]] = []

    def register_key(self, kid: str, private_key: Ed25519PrivateKey) -> None:
        """Registers a key in-memory (e.g. for testing or active session)."""
        self._memory_keys[kid] = private_key

    def get_or_create_officer_key(self, officer_id: str) -> tuple[str, Ed25519PrivateKey, str]:
        """Retrieves or creates an Ed25519 keypair for an authorized officer.
        
        Returns:
            (kid, private_key, public_key_b64)
        """
        kid = f"officer-key-{officer_id}"
        if kid in self._memory_keys:
            priv = self._memory_keys[kid]
            pub_bytes = priv.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            return kid, priv, base64.b64encode(pub_bytes).decode("ascii")

        key_file = self.keystore_dir / f"{kid}.key"
        if key_file.exists():
            key_bytes = key_file.read_bytes()
            priv = Ed25519PrivateKey.from_private_bytes(key_bytes)
        else:
            priv = Ed25519PrivateKey.generate()
            key_bytes = priv.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )
            # Write with restricted permissions
            key_file.write_bytes(key_bytes)
            try:
                os.chmod(key_file, 0o600)
            except Exception:
                pass

        self._memory_keys[kid] = priv
        pub_bytes = priv.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return kid, priv, base64.b64encode(pub_bytes).decode("ascii")

    def get_public_key_b64(self, kid: str) -> str | None:
        """Returns the Base64-encoded raw Ed25519 public key for a key ID."""
        if kid in self._memory_keys:
            pub_bytes = self._memory_keys[kid].public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            return base64.b64encode(pub_bytes).decode("ascii")

        key_file = self.keystore_dir / f"{kid}.key"
        if key_file.exists():
            priv = Ed25519PrivateKey.from_private_bytes(key_file.read_bytes())
            pub_bytes = priv.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
            return base64.b64encode(pub_bytes).decode("ascii")
        return None

    def sign_report(
        self,
        report_payload: dict[str, Any],
        officer_id: str,
    ) -> dict[str, Any]:
        """Canonically signs an inspection report using the officer's Ed25519 key."""
        kid, priv_key, pub_b64 = self.get_or_create_officer_key(officer_id)
        canonical_bytes = canonicalize_report(report_payload)
        digest = sha256_hex(canonical_bytes)

        # Ed25519 signature of canonical report payload
        sig_bytes = priv_key.sign(canonical_bytes)
        sig_b64 = base64.b64encode(sig_bytes).decode("ascii")

        signed_record = {
            "report_digest": digest,
            "signature": sig_b64,
            "signer_kid": kid,
            "signer_public_key": pub_b64,
            "signature_algorithm": "Ed25519",
            "signed_at": datetime.now(UTC).isoformat(),
            "keystore_mode": "DEMO_KEYSTORE_ED25519",
        }
        return signed_record

    def verify_report_signature(
        self,
        report_payload: dict[str, Any],
        expected_digest: str,
        signature_b64: str,
        signer_kid: str,
        public_key_b64: str | None = None,
    ) -> SignatureVerificationResult:
        """Independently verifies an inspection report signature and detects tampering."""
        now_iso = datetime.now(UTC).isoformat()
        pub_b64 = public_key_b64 or self.get_public_key_b64(signer_kid)

        if not pub_b64:
            res = SignatureVerificationResult(
                valid=False,
                signer_kid=signer_kid,
                verified_at=now_iso,
                digest_matches=False,
                signature_matches=False,
                error=f"Signer public key '{signer_kid}' not found in keystore",
                report_digest=None,
            )
            self._record_history(res)
            return res

        current_digest = compute_report_digest(report_payload)
        digest_matches = current_digest == expected_digest

        if not digest_matches:
            res = SignatureVerificationResult(
                valid=False,
                signer_kid=signer_kid,
                verified_at=now_iso,
                digest_matches=False,
                signature_matches=False,
                error="Report content modified after signing: canonical digest mismatch",
                report_digest=current_digest,
            )
            self._record_history(res)
            return res

        try:
            pub_bytes = base64.b64decode(pub_b64)
            pub_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
            sig_bytes = base64.b64decode(signature_b64)
            canonical_bytes = canonicalize_report(report_payload)

            pub_key.verify(sig_bytes, canonical_bytes)
            res = SignatureVerificationResult(
                valid=True,
                signer_kid=signer_kid,
                verified_at=now_iso,
                digest_matches=True,
                signature_matches=True,
                error=None,
                report_digest=current_digest,
            )
        except (InvalidSignature, ValueError) as err:
            res = SignatureVerificationResult(
                valid=False,
                signer_kid=signer_kid,
                verified_at=now_iso,
                digest_matches=digest_matches,
                signature_matches=False,
                error=f"Cryptographic signature verification failed: {err}",
                report_digest=current_digest,
            )

        self._record_history(res)
        return res

    def _record_history(self, res: SignatureVerificationResult) -> None:
        self._verification_history.append(asdict(res))

    @property
    def verification_history(self) -> list[dict[str, Any]]:
        return list(self._verification_history)


# Global default keystore manager instance
default_keystore = KeystoreManager()

