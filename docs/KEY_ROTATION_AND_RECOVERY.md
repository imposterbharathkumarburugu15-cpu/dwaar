# PRAMANA — Key Rotation & Key Compromise Recovery Architecture

## 1. Phased Key Rotation Architecture

### 1.1 The Dual-Requirement Problem
When an organization rotates an encryption or signing key:
1. New documents and tokens must be signed with the fresh key version (`v2`).
2. Documents, Merkle audit checkpoints, JWS QR codes, and offline field inspection packages signed under `v1` must continue to verify without error.
3. If an old key is deleted upon rotation, historical signatures are invalidated, breaking legal admissibility.

### 1.2 PRAMANA Versioned Rotation Engine
PRAMANA solves this through immutable historical key archiving (`backend/pramana/trust/kms.py`):
1. **Version Advancement**: When `rotate_key(key_id="prm-audit-ed25519-v1")` is called:
   - Old key `prm-audit-ed25519-v1` transitions to `RETIRED`.
   - New key `prm-audit-ed25519-v2` is generated and marked `ACTIVE`.
2. **Permanent Public Key Retention**:
   - The old record's `public_key_b64` and `public_key_fingerprint` remain permanently in the SQLite/PostgreSQL `cryptographic_keys` table.
3. **Signing vs. Verification Disambiguation**:
   - `sign_with_key("prm-audit-ed25519-v1")` strictly throws `PermissionError("Cannot sign with key in non-active status RETIRED")`.
   - `verify_with_key("prm-audit-ed25519-v1", data, signature)` succeeds! It loads the retained public key and computes the Ed25519/ECDSA curve verification without error.
4. **Audit Trail**: Every rotation event generates a `KeyRotationEvent` row and an append-only Merkle ledger entry.

---

## 2. Key Compromise & Emergency Recovery Playbook

When private key material is suspected of exposure (e.g., worker memory leak, tablet loss in the field):

### Step 1: Immediate Key Suspension (`raise_security_incident`)
- Administrator calls `POST /api/trust/incidents` with severity `CRITICAL`.
- PRAMANA executes an atomic transaction:
  1. Creates a `SecurityIncident` row with status `OPEN`.
  2. Sets `affected_key.status = "COMPROMISED"`.
  3. Records timestamp `key.compromised_at`.
  4. Any subsequent attempt to use the compromised key for signing is instantly blocked.
  5. Any verification attempt targeting this key alerts the auditor that signatures from this key are compromised and cannot be trusted.

### Step 2: Emergency Recovery Key Generation (`execute_incident_recovery`)
- Administrator executes recovery workflow (`POST /api/trust/incidents/{id}/recover`).
- PRAMANA:
  1. Identifies the compromised key and its purpose.
  2. Increments the version counter and appends `-emergency` tag: `prm-audit-ed25519-v3-emergency`.
  3. Activates the replacement key in the KMS.
  4. Marks the incident status as `RESOLVED`.
  5. Attaches resolution notes and forensic logs to the incident audit trail.

