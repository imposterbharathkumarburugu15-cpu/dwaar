# PRAMANA — PHASE 2 KNOWN LIMITATIONS & SECURITY BOUNDARIES
**Hardware, Statutory, Offline & Cryptographic Realities**  
**SIH 2026 Problem Statement 26261 (AICTE, Regulation Bureau)**  
**Document Reference:** `docs/PHASE_2_KNOWN_LIMITATIONS.md`  

---

## 1. Offline Revocation Guarantee Limitation
* **The Reality:** When a device operates completely offline, it cannot query live Certificate Revocation Lists (CRLs) or Online Certificate Status Protocol (OCSP) responders.
* **PRAMANA's Transparent Handling:** The system strictly reports `revocation_status: "REVOCATION_UNAVAILABLE_OFFLINE"` unless the officer previously synchronized a local revocation snapshot within cache TTL. If a revoked token matches the local snapshot, it displays `REVOKED_ACCORDING_TO_SYNC_DATA`. Stale revocation data is never falsely claimed as real-time validity.

---

## 2. Geolocation Hardware Verification Boundary
* **The Reality:** Standard mobile browsers and consumer tablets report GPS coordinates through software APIs (`navigator.geolocation`) that can be simulated or spoofed via mock location provider apps without hardware-level cryptographic attestation (such as Android Keymaster / SafetyNet / Play Integrity hardware enclave).
* **PRAMANA's Transparent Handling:** Geolocation coordinates captured in field evidence are labeled `device_reported_unverified`. PRAMANA never claims GPS-verified authenticity without genuine cryptographic hardware carrier proofs.

---

## 3. Keystore Hardware Binding
* **The Reality:** In local prototype execution, Ed25519 signing keys are managed by `KeystoreManager` using restricted filesystem demo keys (`data_dir/keystore/`, `chmod 0600`).
* **Production Path:** In production Android tablet deployment, `KeystoreManager` hooks directly into the Android Keystore TEE / StrongBox Keymaster to guarantee non-exportable hardware signing.

---

## 4. Optical QR Decoding Constraints
* **The Reality:** OpenCV QR code detectors can fail on low-resolution, extreme-angle, or blurred paper prints.
* **PRAMANA's Mitigations:** PRAMANA implements multi-scale retries (bicubic 2x, 3x, 4x upscaling and Otsu binarization) and ArUco-based detector fallbacks (`QRCodeDetectorAruco`). Highly damaged or partial QR prints require manual token entry.

