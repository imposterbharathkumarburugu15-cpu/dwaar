# PRAMANA — DIGITAL INSPECTION SIGNING & CRYPTOGRAPHIC SECURITY
**Ed25519 Report Sealing, Canonicalization & Keystore Abstraction**  
**SIH 2026 Problem Statement 26261 (AICTE, Regulation Bureau)**  
**Document Reference:** `docs/DIGITAL_SIGNING_SECURITY.md`  

---

## 1. Cryptographic Signing Overview

A critical vulnerability in inspection systems is post-inspection tampering: an unprincipled actor altering field observations, workstation counts, or land dimensions after the regulatory officer has completed their visit.

PRAMANA eliminates this attack surface through **Source-Level Cryptographic Sealing**:
1. All inspection checklist items, notes, recommendations, and evidence digests are serialized into a canonical representation.
2. The canonical payload is hashed using SHA-256.
3. The resulting digest is signed with the regulatory officer's private Ed25519 key.
4. Any post-signing alteration invalidates the mathematical signature.

---

## 2. Canonicalization Specification (RFC 8785)

JSON representations naturally permit arbitrary whitespace, varying key orders, and float precision quirks. PRAMANA enforces deterministic JSON canonicalization per RFC 8785:

```python
def canonicalize_report(payload: dict[str, Any]) -> bytes:
    def _sort(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _sort(v) for k, v in sorted(obj.items())}
        if isinstance(obj, list):
            return [_sort(x) for x in obj]
        return obj

    sorted_obj = _sort(payload)
    return json.dumps(sorted_obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
```

### Properties Guaranteed:
* **Lexicographic Key Ordering:** All dictionary keys sorted recursively at all depths.
* **Zero Extraneous Whitespace:** Strict `separators=(",", ":")` elimination.
* **UTF-8 Byte Encoding:** Deterministic multi-byte sequence generation.

---

## 3. Ed25519 (EdDSA) Digital Signatures

PRAMANA adopts **Ed25519 (RFC 8037)** over legacy RSA-2048:
* **Fast Computation:** 1.5ms per signature on tablet CPU cores.
* **Compact Footprint:** 64-byte raw signature, 32-byte public key (ideal for low-bandwidth rural sync and QR encoding).
* **Strong Collision Resistance:** Curve25519 curve security immune to side-channel timing attacks.

---

## 4. Keystore Abstraction & Security Boundaries

Private keys must never be embedded in frontend client code, exposed in browser logs, or transmitted over API requests.

PRAMANA implements the `KeystoreManager` abstraction:

```
+-------------------------------------------------------------------------------+
|                             KEYSTORE ABSTRACTION                              |
+-------------------------------------------------------------------------------+
                                        |
       +--------------------------------+--------------------------------+
       |                                                                 |
       v                                                                 v
[ DEMO_KEYSTORE_ED25519 ]                                      [ PRODUCTION HARNESS ]
- Local filesystem storage (`data_dir/keystore/`)              - Android Keystore Hardware TEE
- File permissions restricted (`chmod 0600`)                   - Hardware Security Module (HSM)
- In-memory key caching during active sessions                 - FIPS 140-3 Level 3 Hardware Security
- Clearly labeled with demo provenance                         - Non-exportable hardware private keys
```

### Security Guarantees:
1. **Never Embedded in Code:** No hardcoded private keys exist in any frontend or backend source file.
2. **Key Identifier Indexing:** Inspection reports store only `signer_kid` (e.g. `officer-key-officer_sharma`) and the signature. Public keys are resolved via trust stores.
3. **Verification History Tracking:** All signature verification attempts (passes and failures) are appended to an immutable in-memory verification ledger.

