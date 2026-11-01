# PRAMANA — OFFLINE FIELD SCRUTINY ARCHITECTURE
**Autonomous Remote Inspection & Local Cryptographic Integrity**  
**SIH 2026 Problem Statement 26261 (AICTE, Regulation Bureau)**  
**Document Reference:** `docs/OFFLINE_FIELD_ARCHITECTURE.md`  

---

## 1. Architectural Philosophy

Rural educational institutions in India often reside in remote geographical zones with unstable or absent cellular connectivity (2G/intermittent 4G). Regulatory physical visits cannot rely on persistent cloud roundtrips.

PRAMANA implements an **Autonomous Offline-First Architecture**:
1. **Zero Cloud Latency on Site:** Regulatory officers download a self-contained Case Investigation Bundle before embarking on field visits.
2. **Local Dual-Tier Persistence:**
   - **Browser Tier:** IndexedDB structured database storing case checklists, observation drafts, and encrypted attachments.
   - **Backend / Tablet Runtime Tier:** SQLite relational tables (`field_inspection_cases`, `inspection_evidence`, `offline_sync_events`, `offline_revocation_cache`).
3. **Cryptographic Sealing at Source:** Observations and evidence are fingerprinted and digitally signed on the local tablet using Ed25519 before transmission.
4. **Deterministic Reconciliation:** When network connectivity is re-established, the synchronization engine ingests events with strict idempotency and surfaces explicit side-by-side conflict resolution.

---

## 2. System Architecture Flow

```
+-----------------------------------------------------------------------------------+
|                        ONLINE PRE-INSPECTION PREPARATION                          |
|                                                                                   |
|  AICTE Central Server                                    Officer Tablet / Browser |
|  +--------------------+                                  +---------------------+  |
|  | Application Record | ---- [GET /offline/bundle/{id}] ---> | Case Pack Exporter  |  |
|  | Declared Claims    |                                  | IndexedDB Cache     |  |
|  | Extracted OCR Text |                                  | Local Trust Store   |  |
|  +--------------------+                                  +---------------------+  |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
|                        OFFLINE ON-SITE PHYSICAL SCRUTINY                          |
|                                                                                   |
|  1. Physical Checklist Audit: Land, Built-up Area, Labs, Fire NOC, Bandwidth     |
|  2. Evidence Capture: Camera photos & documents hashed (SHA-256, pHash, dHash)    |
|  3. Offline QR Check: JWS Ed25519 validated against cached public keys            |
|  4. Digital Signing: RFC 8785 Canonicalization + Ed25519 Signature computed      |
|  5. Local Queue: Encrypted offline events staged in IndexedDB with device UUIDs   |
+-----------------------------------------------------------------------------------+
                                         |
                                         v
+-----------------------------------------------------------------------------------+
|                        RECONNECTION & SECURE RECONCILIATION                       |
|                                                                                   |
|  Officer Tablet / Browser                                AICTE Central Server     |
|  +---------------------+                                 +---------------------+  |
|  | Staged Event Queue  | ---- [POST /offline/sync/batch] -> | Idempotency Gate    |  |
|  | Device Event IDs    |                                 | Conflict Detector   |  |
|  | Signed Reports      | <--- [Verifiable Sync Receipt] -+ | Merkle Audit Append |  |
|  +---------------------+                                 +---------------------+  |
+-----------------------------------------------------------------------------------+
```

---

## 3. Core Database Schemas

### 1. `field_inspection_cases`
Holds the authorized on-site physical scrutiny instance:
* `id`: Primary key (`ins_...`).
* `case_number`: Unique identifier (e.g. `INSP-2026-000107-01`).
* `application_id`: Scrutinized application reference.
* `institution_id`: Target institution.
* `assigned_officer_id`: Regulatory officer ID.
* `status`: `draft`, `in_progress`, `completed`, `signed`, `synced`, `conflict_detected`.
* `checklist`: JSON array of checklist items (`item_id`, `title`, `declared_value`, `observed_value`, `status`, `notes`).
* `observations`: JSON array of time-stamped observation logs.
* `report_digest`: SHA-256 digest of canonical report JSON.
* `signature`: Base64-encoded Ed25519 digital signature.
* `signer_kid`: Key identifier of the officer.

### 2. `inspection_evidence`
Tracks all physical artifacts collected during field visits:
* `id`: Primary key (`evd_...`).
* `inspection_id`: Foreign key to inspection case.
* `device_event_id`: Device-generated UUID for sync deduplication.
* `category`: `image`, `document`, `inspection_note`, `supporting_attachment`.
* `sha256`: Cryptographic byte hash.
* `phash` & `dhash`: 16-bit perceptual and gradient difference image hashes.
* `metadata_json`: Device details, honest geolocation provenance, and detected duplicates.
* `verification_status`: `verified_valid` or `duplicate_flagged`.

### 3. `offline_sync_events`
Durable synchronization log:
* `event_id`: Unique client device UUID.
* `status`: `pending`, `synchronized`, `conflict_detected`, `requires_review`, `resolved`, `rejected`.
* `conflict_type`: Category of detected discrepancy.
* `receipt_id`: Unique audit receipt issued upon ingestion.

---

## 4. Evidence Fingerprinting & Duplicate Detection

When an inspector takes a photo or attaches an on-site document:
1. **SHA-256:** Computed immediately over raw file bytes. Identifies exact bit-for-bit file duplicates.
2. **Perceptual Hash (pHash):** 16x16 DCT-based image hash. Robust against compression, minor brightness shifts, and resizing.
3. **Difference Hash (dHash):** 16x16 gradient difference hash. Robust against slight cropping and aspect ratio tweaks.
4. **Threshold Matching:**
   $$\text{Hamming Distance}(\text{hash}_A, \text{hash}_B) \le 5 \implies \text{PERCEPTUAL\_NEAR\_DUPLICATE}$$
   When a duplicate is detected across current or peer institutions, the evidence is tagged `duplicate_flagged` without deleting original evidence.

