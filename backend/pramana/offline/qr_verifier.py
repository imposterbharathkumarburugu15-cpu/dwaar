"""Offline Signed QR Verification Engine for PRAMANA Field Scrutiny.

Implements Module 4 of Phase 2:
- Offline JWS Ed25519 signature verification against local cached issuer keys.
- Credential integrity checking.
- Expiration validation (`exp` claim).
- Separate revocation status reporting:
  * SIGNATURE_VALID
  * SIGNATURE_INVALID
  * EXPIRED
  * ISSUER_UNKNOWN
  * REVOCATION_UNAVAILABLE_OFFLINE
  * REVOKED_ACCORDING_TO_SYNC_DATA
- Explicit warnings against assuming offline revocation guarantees real-time validity.
"""

import base64
import json
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ..verification import signed_qr


def _unb64u(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


@dataclass
class OfflineQrVerificationResult:
    status: str
    signature_valid: bool
    expired: bool
    issuer_known: bool
    revocation_status: str
    kid: str | None
    issuer: dict[str, Any] | None
    payload: dict[str, Any] | None
    error: str | None
    verified_at: str
    offline_revocation_notice: str
    last_sync_timestamp: str | None = None


def verify_qr_offline(
    token_or_link: str,
    revocation_cache: dict[str, Any] | None = None,
    current_timestamp: float | None = None,
) -> OfflineQrVerificationResult:
    """Performs offline verification of an issuer-signed QR token.
    
    Args:
        token_or_link: Raw JWS token or full scan link URL
        revocation_cache: Local dictionary mapping token JTI or cert ID to revocation details
        current_timestamp: Optional unix timestamp for expiry checking (defaults to time.time())
    """
    now = current_timestamp if current_timestamp is not None else time.time()
    now_iso = datetime.now(UTC).isoformat()
    raw_token = signed_qr.extract_token(token_or_link)

    parts = raw_token.split(".")
    if len(parts) != 3:
        return OfflineQrVerificationResult(
            status="SIGNATURE_INVALID",
            signature_valid=False,
            expired=False,
            issuer_known=False,
            revocation_status="REVOCATION_UNAVAILABLE_OFFLINE",
            kid=None,
            issuer=None,
            payload=None,
            error="Malformed token: expected 3-part compact JWS",
            verified_at=now_iso,
            offline_revocation_notice="Offline verification cannot guarantee real-time revocation status without live server synchronization.",
        )

    try:
        header = json.loads(_unb64u(parts[0]))
        payload = json.loads(_unb64u(parts[1]))
    except Exception as err:
        return OfflineQrVerificationResult(
            status="SIGNATURE_INVALID",
            signature_valid=False,
            expired=False,
            issuer_known=False,
            revocation_status="REVOCATION_UNAVAILABLE_OFFLINE",
            kid=None,
            issuer=None,
            payload=None,
            error=f"Failed to decode token header or payload: {err}",
            verified_at=now_iso,
            offline_revocation_notice="Offline verification cannot guarantee real-time revocation status.",
        )

    kid = header.get("kid")
    alg = header.get("alg")
    if alg != "EdDSA":
        return OfflineQrVerificationResult(
            status="SIGNATURE_INVALID",
            signature_valid=False,
            expired=False,
            issuer_known=False,
            revocation_status="REVOCATION_UNAVAILABLE_OFFLINE",
            kid=kid,
            issuer=None,
            payload=payload,
            error=f"Unsupported algorithm '{alg}', expected EdDSA",
            verified_at=now_iso,
            offline_revocation_notice="Offline verification cannot check revocation for unsupported algorithms.",
        )

    # 1. Issuer Key Resolution
    keys = signed_qr.issuer_keys()
    issuer_info = keys.get(kid or "")
    if not issuer_info:
        return OfflineQrVerificationResult(
            status="ISSUER_UNKNOWN",
            signature_valid=False,
            expired=False,
            issuer_known=False,
            revocation_status="REVOCATION_UNAVAILABLE_OFFLINE",
            kid=kid,
            issuer=None,
            payload=payload,
            error=f"Issuer public key '{kid}' is not present in local trust store",
            verified_at=now_iso,
            offline_revocation_notice="Issuer unknown; offline revocation status is not available.",
        )

    # 2. Cryptographic Signature Verification
    try:
        pub_bytes = base64.b64decode(issuer_info["public_key"])
        pub_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        sig_bytes = _unb64u(parts[2])
        pub_key.verify(sig_bytes, f"{parts[0]}.{parts[1]}".encode())
    except (InvalidSignature, ValueError) as err:
        return OfflineQrVerificationResult(
            status="SIGNATURE_INVALID",
            signature_valid=False,
            expired=False,
            issuer_known=True,
            revocation_status="REVOCATION_UNAVAILABLE_OFFLINE",
            kid=kid,
            issuer=issuer_info,
            payload=payload,
            error=f"Cryptographic signature check failed: {err}",
            verified_at=now_iso,
            offline_revocation_notice="Signature is cryptographically invalid.",
        )

    # 3. Expiration Check
    exp = payload.get("exp")
    if exp is not None and float(exp) < now:
        return OfflineQrVerificationResult(
            status="EXPIRED",
            signature_valid=True,
            expired=True,
            issuer_known=True,
            revocation_status="REVOCATION_UNAVAILABLE_OFFLINE",
            kid=kid,
            issuer=issuer_info,
            payload=payload,
            error=f"Credential expired at {datetime.fromtimestamp(float(exp), UTC).isoformat()}",
            verified_at=now_iso,
            offline_revocation_notice="Credential is expired. Offline revocation status not evaluated.",
        )

    # 4. Revocation Status Handling
    revocation_status = "REVOCATION_UNAVAILABLE_OFFLINE"
    status_label = "SIGNATURE_VALID"
    last_sync = None

    if revocation_cache:
        last_sync = revocation_cache.get("last_sync_timestamp")
        revoked_items = revocation_cache.get("revoked_items", {})
        
        token_id = payload.get("jti") or payload.get("sub") or payload.get("doc_id")
        if token_id and token_id in revoked_items:
            rev_info = revoked_items[token_id]
            revocation_status = "REVOKED_ACCORDING_TO_SYNC_DATA"
            status_label = "REVOKED_ACCORDING_TO_SYNC_DATA"
            return OfflineQrVerificationResult(
                status=status_label,
                signature_valid=True,
                expired=False,
                issuer_known=True,
                revocation_status=revocation_status,
                kid=kid,
                issuer=issuer_info,
                payload=payload,
                error=f"Credential was revoked according to last synced data: {rev_info.get('reason', 'Revoked')}",
                verified_at=now_iso,
                offline_revocation_notice=f"Revocation status reflects offline snapshot synced at {last_sync or 'unknown time'}.",
                last_sync_timestamp=last_sync,
            )

    return OfflineQrVerificationResult(
        status=status_label,
        signature_valid=True,
        expired=False,
        issuer_known=True,
        revocation_status=revocation_status,
        kid=kid,
        issuer=issuer_info,
        payload=payload,
        error=None,
        verified_at=now_iso,
        offline_revocation_notice="Signature is cryptographically valid. Real-time revocation status cannot be verified while offline.",
        last_sync_timestamp=last_sync,
    )
