# PRAMANA — Key Management Service (KMS) Architecture

## 1. Overview
The PRAMANA Key Management Service (`backend/pramana/trust/kms.py`) provides centralized cryptographic key generation, storage, usage tracking, lifecycle state management, and envelope key orchestration across all regulatory processes.

## 2. Key Lifecycle State Machine

```
              ┌───────────────────────────┐
              │         GENERATED         │
              └─────────────┬─────────────┘
                            │ (activate)
                            ▼
              ┌───────────────────────────┐
       ┌─────▶│          ACTIVE           │◀──────┐
       │      └─────────────┬─────────────┘       │
(abort rotation)            │ (rotate / pending)  │
       │                    ▼                     │
       │      ┌───────────────────────────┐       │
       └──────│     ROTATION_PENDING      │───────┘
              └─────────────┬─────────────┘ (grace period expired)
                            │
                            ▼
              ┌───────────────────────────┐
              │          RETIRED          │ (retained for verification)
              └─────────────┬─────────────┘
                            │
              ┌─────────────┴─────────────┐
              ▼                           ▼
┌───────────────────────────┐   ┌───────────────────────────┐
│          REVOKED          │   │        COMPROMISED        │
└─────────────┬─────────────┘   └─────────────┬─────────────┘
              │                               │
              └─────────────┬─────────────────┘
                            ▼
              ┌───────────────────────────┐
              │         ARCHIVED          │
              └───────────────────────────┘
```

### State Definitions & Enforcements:
- **`GENERATED`**: Key material created and registered in the KMS; awaiting deployment readiness or activation checks. Cannot sign.
- **`ACTIVE`**: The current default key used for creating digital signatures (Ed25519, ECDSA) and document envelope encryption (AES-256-GCM). Usage count and timestamp are updated upon every invocation.
- **`ROTATION_PENDING`**: A transitional state during phased migration where both old and new keys may be recognized, allowing clients and inspection tablets to synchronize without downtime.
- **`RETIRED`**: Key superseded by a newer version. **Critically, signing with retired keys is strictly rejected (`PermissionError`), but signature verification remains 100% supported** because historical public keys are permanently preserved.
- **`REVOKED`**: Key permanently invalidated due to policy deprecation or administrative decision.
- **`COMPROMISED`**: Key identified as leaked, extracted, or exposed. Instantly suspended by incident response. Verification of signatures created by compromised keys is flagged as untrusted.
- **`ARCHIVED`**: Cold storage state for decommissioned historical keys.

## 3. Cryptographic Primitives & Purposes

| Key Purpose | Algorithm | Curve / Mode | Usage Scenario |
|---|---|---|---|
| `audit_signing` | Ed25519 | Edwards-curve (Ed25519) | Merkle tree checkpoint and ledger receipt signing |
| `qr_issuance` | Ed25519 / EdDSA | Ed25519 (JWS RFC 8037) | JWS-compact QR code signing for institution credentials |
| `officer_field_signing` | ECDSA_P256 | NIST P-256 + SHA-256 | Regulatory officer field inspection reports and attestations |
| `document_envelope` | AES_256_GCM | 256-bit GCM (RFC 5116) | Master key for per-document envelope encryption |

## 4. Zero Key Leakage Security Policy
1. Private key material is never returned across REST APIs or logged in audit entries.
2. Only safe public metadata (`key_id`, `algorithm`, `version`, `status`, `public_key_b64`, `public_key_fingerprint`, `usage_count`) is exposed via `/api/trust/keys`.
3. In production, private keys never leave the secure hardware boundary of the HSM; signing is performed via PKCS#11 function pointers.

