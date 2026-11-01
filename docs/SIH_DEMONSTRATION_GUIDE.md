# PRAMANA — SIH 2026 Master Demonstration Guide

## Demonstration Scenario: "The Autonomous & Explainable Regulatory Journey"
This walkthrough demonstrates the complete end-to-end functionality of PRAMANA for evaluators and regulatory authorities.

### Step 1: Enterprise Multi-Tenant Onboarding
- Administrator navigates to Admin portal.
- Onboards a new technical institution: `SIH National Institute of Robotics & AI` (AICTE ID: `1-SIH-2026-DEMO`).
- Enforces password complexity policy and provisions the institution admin account.

### Step 2: Cross-Document Intelligence & Consistency Analysis
- Applicant uploads application package (Land Deed, Fire NOC, Society Registration, Architect Certificate).
- PRAMANA executes the Cross-Document Consistency Engine:
  - Cross-references Society Name across Trust Deed and application.
  - Verifies exact Land Survey coordinates across Revenue Deed and Fire NOC.
  - Confirms chronological sanity (land acquisition date post-dates society incorporation).

### Step 3: Explainable 6-Dimensional Risk Intelligence
- Officer views the Trust & Risk Observatory:
  - Decomposes risk across 6 orthogonal dimensions: Document Authenticity, Institutional Identity, Regulatory Compliance, Data Consistency, Historical Evidence, External Verification.
  - Provides itemized contributing factors and direct clickable links to supporting evidence.
  - Highlights explicit disclaimer: "Decision support only. Human authority preserved."

### Step 4: Purpose-Bound Consent & 12-Step Government Verification
- System validates purpose-bound consent from the applicant.
- Executes the canonical 12-step government verification pipeline against API Setu and DigiLocker adapters.
- Emits cryptographically verifiable verdict (`VERIFIED_BY_AUTHORIZED_ISSUER`).

### Step 5: What-If Regulatory Policy Simulation
- Officer tests proposed handbook amendment (e.g. tightening Faculty-to-Student Ratio from 1:20 to 1:15).
- System forecasts compliance impacts across applications without mutating live records.

### Step 6: Final Digital Signing & Merkle Audit Ledger Checkpoint
- Regulatory officer approves scrutiny findings.
- Generates Ed25519 digitally signed inspection report and JWS EdDSA verifiable QR payload.
- Merkle audit ledger verifies 100% hash chain continuity from genesis block.

