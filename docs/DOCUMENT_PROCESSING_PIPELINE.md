# Distributed 12-Stage Document Processing Pipeline

## Pipeline Canonical Stages

The PRAMANA distributed document processing pipeline executes 12 verifiable, auditable stages:

| Stage Index | Stage Name | Description | Key Output Artifact |
| :---: | :--- | :--- | :--- |
| **1** | `DOCUMENT_UPLOADED` | Ingestion, chunked streaming, file size verification | Raw byte payload, SHA-256 |
| **2** | `DOCUMENT_VALIDATION` | Corrupt header checks, size bounds (max 50MB) | Format valid flag |
| **3** | `FILE_TYPE_VERIFICATION` | Magic byte analysis (PDF, PNG, JPEG whitelisting) | Validated MIME type |
| **4** | `MALWARE_SCAN_ADAPTER` | Heuristic scan for malicious `/JavaScript` and `/Launch` | Clean status |
| **5** | `OCR_EXTRACTION` | RapidOCR English and Hindi (Devanagari script) | Extracted text tokens |
| **6** | `TEXT_NORMALIZATION` | Unicode NFC normalization, whitespace normalization | Normalized text stream |
| **7** | `DOCUMENT_FINGERPRINTING`| Perceptual hashing (pHash) and MinHash shingling | Deduplication hash |
| **8** | `FORENSIC_ANALYSIS` | C2PA provenance, Error Level Analysis (ELA) | Forensic authenticity score |
| **9** | `FACT_EXTRACTION` | Structural field extraction (land acres, built-up area) | Normalized fact dictionary |
| **10**| `REGULATORY_RULE_VALIDATION`| Rule engine evaluation against AICTE Approval Process | Rule pass/fail records |
| **11**| `RISK_SCORING` | Risk matrix tier assignment (Tier 1-4) | Overall risk percentage |
| **12**| `FINAL_SCRUTINY_RESULT` | Recommendation synthesis for AICTE scrutiny officers | Final scrutiny report |

## Stage-Level Persistence & Resumption

Every stage writes its execution status, duration, input SHA-256, and output metadata into the `document_pipeline_stages` database table. If processing fails midway (e.g. stage 7), workers can resume execution starting specifically from the failed stage using `resume_from_stage="DOCUMENT_FINGERPRINTING"`.

