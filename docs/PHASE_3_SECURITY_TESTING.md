# PRAMANA — Phase 3 Security & Cryptographic Testing Report

## 1. Test Suite Summary
The Phase 3 trust and hardware security layer is validated by 7 dedicated test suites comprising 31 unit, integration, and security tests.

| Test File | Modules Tested | Tests | Result |
|---|---|:---:|:---:|
| `tests/test_kms_lifecycle.py` | Key generation, state machine transitions, invalid transition prevention, usage tracking, key listing | 5 | **PASSED** |
| `tests/test_hsm_abstraction.py` | Local provider, PKCS#11 degraded health reporting, signature generation, envelope encryption/decryption, provider registry | 5 | **PASSED** |
| `tests/test_key_rotation.py` | Key rotation v1->v2, historical verification preservation, retirement block on signing | 3 | **PASSED** |
| `tests/test_certificate_management.py` | X.509 registration & metadata, trusted anchor validation, expired cert rejection, self-signed rejection, chain validation, forged signature rejection | 6 | **PASSED** |
| `tests/test_crl_ocsp.py` | CRL synchronization & DB updates, anti-rollback protection, signature verification, expired CRL detection, offline snapshot check | 5 | **PASSED** |
| `tests/test_trust_store_recovery.py` | Scoped trust store versioning, key compromise suspension, emergency replacement key recovery | 3 | **PASSED** |
| `tests/test_trust_security_roles.py` | RBAC: Admin rotation, non-admin 403 Forbidden, unauthenticated 401 Unauthorized, zero private key leakage | 4 | **PASSED** |
| **Total Phase 3 Tests** | **Modules 1 – 10** | **31** | **PASSED (100%)** |

---

## 2. Security Test Highlights & Assertions

### 2.1 Anti-Rollback Verification (`test_anti_rollback_protection`)
- **Action**: Synchronizes CRL #5, then submits older CRL #3 and duplicate CRL #5.
- **Assertion**: Both replay attempts are rejected with `ROLLBACK_ATTEMPT`, `is_rollback=True`, and descriptive error strings.

### 2.2 Historical Signature Verification (`test_historical_signatures_remain_verifiable_after_rotation`)
- **Action**: Signs payload under `v1`, rotates to `v2` (transitioning `v1` to `RETIRED`).
- **Assertion**:
  - `verify_with_key("prm-test-v1", payload, sig)` returns `True`.
  - `sign_with_key("prm-test-v1", payload)` raises `PermissionError`.

### 2.3 Compromise Isolation (`test_key_compromise_and_incident_raising`)
- **Action**: Raises critical incident on `prm-test-compromise-v1`.
- **Assertion**: Key status is immediately set to `COMPROMISED`; `sign_with_key` immediately raises `PermissionError`.

### 2.4 RBAC Isolation (`test_non_admin_forbidden_from_rotating_key`)
- **Action**: Institution Admin (`inst_admin`) and External Verifier (`ext_verifier`) attempt to invoke `/api/trust/keys/{id}/rotate` and `/revoke`.
- **Assertion**: Both receive HTTP `403 Forbidden`.

