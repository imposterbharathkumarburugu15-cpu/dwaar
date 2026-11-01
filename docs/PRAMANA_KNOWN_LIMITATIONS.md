# PRAMANA — KNOWN LIMITATIONS & ARCHITECTURAL CONSTRAINTS
**Transparent Boundary Analysis, Simulation Disclosures & Production Dependencies**  
**SIH 2026 Problem Statement 26261 (AICTE, Regulation Bureau)**  
**Document Reference:** `docs/PRAMANA_KNOWN_LIMITATIONS.md`  
**Phase:** Phase 1 — Stabilization & Feature Completion Baseline  
**Date:** November 1, 2026  

---

## 1. Architectural Integrity & Disclosure Mandate

PRAMANA adheres to an uncompromising standard of technical honesty. In government regulatory technology, representing simulated or heuristic capabilities as live production integrations undermines audit credibility. 

This document defines the clear boundaries, operational constraints, and statutory exclusions of the PRAMANA prototype.

---

## 2. External Government Registries & Network Integrations

| Registry / Gateway | Current State in Prototype | Concrete Technical Implementation | Why It Is Not Live in Prototype | Production Onboarding Path |
|---|---|---|---|---|
| **DigiLocker / API Setu Gateway** | **Simulated Gateway Adapter** | [`backend/pramana/verification/issuer.py`](file:///c:/Users/bhara/Downloads/praman/pramana/backend/pramana/verification/issuer.py) resolves document URIs via local registry cache. | MeitY API Setu Standard Operating Procedures strictly require verified institutional entity KYC; sandbox API keys are not issued for hackathon participation. | Formal AICTE entity onboarding on API Setu; exchange of mutual TLS (mTLS) certificates and client credentials. |
| **State Fire Safety Portals** | **High-Fidelity Simulated Adapter** | Simulates state fire department clearance verification callbacks (`[SIMULATED_GATEWAY]`). | State fire portals (e.g., Telangana TG-FIRENOC, Maharashtra Fire Services) operate web portals with CAPTCHAs and session tokens without public REST APIs. Web scraping is prohibited by Terms of Service. | Formal inter-departmental State Government API data-sharing agreements or reliance on PRAMANA's certified manual officer verification workflow. |
| **SHCIL e-Stamping Verification** | **Simulated Registry & Officer Fallback** | Simulates Stock Holding Corporation of India Limited certificate number lookups. | Direct automated queries without organizational authorization violate SHCIL Terms of Service and access control rules. | Enterprise API agreement with SHCIL. |
| **Online OCSP / CRL Revocation** | **Bundled Offline PKI (Online Optional)** | [`backend/pramana/verification/signature.py`](file:///c:/Users/bhara/Downloads/praman/pramana/backend/pramana/verification/signature.py) validates CMS/PAdES signatures against bundled CCA India roots (2014, 2015, 2022). | Field verification environments often operate in air-gapped or restricted networks where outbound OCSP requests timeout. | Set `pki_fetch_revocation=True` in production environments with verified outbound internet access to eMudhra, (n)Code, and Capricorn responders. |

---

## 3. Cryptographic & Key Management Constraints

### 3.1 Software Envelope Encryption vs. Hardware Security Module (HSM)
* **Current Implementation:** Per-document envelope encryption using `AES-256-GCM` data encryption keys (DEK) wrapped with a rotatable master key (`keyring.py`) stored locally.
* **Production Constraint:** For national AICTE deployment handling hundreds of thousands of institutional filings, FIPS 140-2 Level 3 Hardware Security Module (HSM) key management is required.
* **Mitigation:** The `keyring.py` envelope encryption interface cleanly abstracts key wrapping, enabling seamless migration to PKCS#11 or cloud KMS (AWS CloudHSM, Google Cloud KMS) without schema changes.

### 3.2 Statutory Biometric Exclusion
* **Current Implementation:** PRAMANA does **NOT** ingest, store, or match raw Aadhaar numbers or biometric templates.
* **Legal Mandate:** Under Section 8A(4) of the Aadhaar Act and Section 6 of the DPDP Act 2023, non-statutory biometric collection is legally prohibited.
* **Prototype Design:** PRAMANA employs privacy-preserving, salted cryptographic identity tokens (`FAC-SYN-xxxx`) and perceptual image hashing for faculty roster deduplication.

---

## 4. Artificial Intelligence & Computer Vision Boundaries

### 4.1 C2PA Content Credentials Hardware Dependencies
* **Status:** Fully functional parser and verification engine ([`photos/credentials.py`](file:///c:/Users/bhara/Downloads/praman/pramana/backend/pramana/photos/credentials.py)).
* **Limitation:** In the real world, most commodity mobile phones used by college staff do not yet embed C2PA hardware provenance manifests.
* **Policy Rule:** Missing C2PA manifests are treated as neutral unverified provenance and are **NEVER** labeled as proof of forgery or fraud.

### 4.2 YOLOX-M Object Detection Constraints
* **Status:** Model architecture and pretrained ONNX weights ([`models/yolox_m.onnx`](file:///c:/Users/bhara/Downloads/praman/pramana/backend/models/yolox_m.onnx)) execute locally on CPU via onnxruntime.
* **Limitation:** Object detectors see only visible objects within camera field-of-view; cubicle dividers, wide-angle lens distortions, or unphotographed sections of a computer lab can cause partial workstation counts.
* **Policy Rule:** YOLOX workstation counts serve as low-weight investigatory indicators for scrutiny officers and never override primary documentary evidence (purchase invoices, stock ledgers).

---

## 5. Summary

These documented limitations represent responsible regulatory engineering, ensuring that PRAMANA operates safely, defensibly, and within statutory boundaries.

