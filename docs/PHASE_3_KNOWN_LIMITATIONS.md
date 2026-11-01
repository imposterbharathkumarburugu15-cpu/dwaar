# PRAMANA — Phase 3 Known Limitations & Production Readiness Notes

## 1. Physical Hardware Connection Limitation
- **Status**: Simulated via `LocalDevelopmentCryptoProvider` using OpenSSL cryptography primitives.
- **Limitation**: In the local development and demonstration environment, no physical FIPS 140-3 Level 3/4 hardware security module (e.g. Nitrokey HSM, YubiHSM, Thales Luna) is physically connected to the host machine.
- **Honest Mitigation**: The system explicitly reports `is_hardware_backed: false` and `provider_type: "DEVELOPMENT_PROVIDER"` across all status endpoints and dashboard UI components. When the PKCS#11 adapter is queried without a hardware dongle, it returns `HARDWARE_NOT_CONNECTED` rather than feigning hardware connectivity.

## 2. Public CA Live Network Queries
- **Status**: Local & Cached PKI snapshot validation.
- **Limitation**: Live automated network fetching from external commercial CAs (e.g., Let's Encrypt, DigiCert, NIC CA) via AIA URLs is disabled in local mode to maintain 100% offline self-containment.
- **Mitigation**: PRAMANA provides manual CRL upload and synchronization via `/api/trust/crl/sync`, allowing administrators to ingest real CA revocation lists offline or via scheduled local batch workers.

## 3. OCSP Stapling in Non-TLS Contexts
- **Status**: Implemented as raw bytes verification abstraction (`verify_ocsp_response_bytes()`).
- **Limitation**: Web browsers visiting PRAMANA over HTTP do not perform OCSP stapling at the HTTP transport layer; OCSP evaluation is handled at the application layer when checking external verifier credential packets.

## 4. Single-Admin Key Rotation Policy
- **Status**: Role-based access control requires `super_admin` or `aicte_admin`.
- **Limitation**: Advanced m-of-n multi-party authorization (Shamir's Secret Sharing or dual-custody approval quorum) for key rotation is scheduled for enterprise governance phases; currently, a single authenticated Super Admin can authorize a rotation.

