# 12-Step Government Document Verification Engine

## Canonical 12 Stages
1. `DOCUMENT_RECEIVED`: Ingestion of raw document payload.
2. `SOURCE_IDENTIFICATION`: Resolution of destination authority and adapter.
3. `AUTHORIZATION_CHECK`: Active, unexpired consent verification.
4. `DOCUMENT_HASHING`: Chunked SHA-256 computation.
5. `FILE_FORMAT_VALIDATION`: PDF/XML binary structure validation.
6. `SIGNATURE_VALIDATION`: Cryptographic signature verification.
7. `ISSUER_VALIDATION`: Issuer verification against trust anchors.
8. `CERTIFICATE_CHAIN_VALIDATION`: Root-to-leaf X.509 path validation with CRL/OCSP.
9. `METADATA_EXTRACTION`: Extraction of verified fields from official response.
10. `CROSS_DOCUMENT_COMPARISON`: Comparison between application claims and registry data.
11. `REGULATORY_RULE_CHECK`: Checking AICTE regulatory thresholds.
12. `VERIFICATION_RESULT`: Persisting verifiable outcome record and audit ledger commit.

