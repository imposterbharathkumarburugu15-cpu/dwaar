# PRAMANA — X.509 Certificate & PKI Trust Architecture

## 1. Architectural Scope
Module 4 (`backend/pramana/trust/certificates.py`) provides end-to-end X.509 Public Key Infrastructure (PKI) management conforming to RFC 5280. It manages root trust anchors, intermediate certificate authorities, and leaf credentials used for institutional identity validation, regulatory officer tablets, and external verifier assertions.

---

## 2. Certificate Lifecycle & Metadata Extraction
When an X.509 certificate PEM is registered via `register_certificate()`:
1. **ASN.1 Parsing**: Parsed using `cryptography.x509.load_pem_x509_certificate`.
2. **Metadata Canonicalization**:
   - `subject_dn`: RFC 4514 canonical DN string (e.g. `CN=PRAMANA Root CA,O=AICTE,C=IN`).
   - `issuer_dn`: RFC 4514 issuer DN string.
   - `serial_number`: Positive decimal serial string.
   - `fingerprint_sha256`: SHA-256 digest of raw DER bytes for tamper-proof index lookup.
   - `not_before` / `not_after`: UTC timestamps representing the certificate validity period.
3. **Extension Parsing**:
   - Extracts CRL Distribution Points (`X509.ExtensionOID.CRL_DISTRIBUTION_POINTS`).
   - Extracts Authority Information Access (AIA) OCSP responder URLs (`ExtensionOID.AUTHORITY_INFORMATION_ACCESS`).

---

## 3. Cryptographic Chain Validation Workflow

```
   ┌────────────────────────────────────────────────────────┐
   │                  Inbound X.509 PEM                     │
   └───────────────────────────┬────────────────────────────┘
                               │
                               ▼
        [Step 1] ASN.1 Structure Check & Expiration Check
               (now < not_before or now > not_after)
                               │
            ┌──────────────────┴──────────────────┐
        [Invalid]                              [Valid]
            ▼                                     ▼
   Return EXPIRED / NOT_YET_VALID      [Step 2] Self-Signed Check
                                       (subject_dn == issuer_dn)
                                                  │
                                ┌─────────────────┴─────────────────┐
                             [True]                              [False]
                                │                                   │
                                ▼                                   ▼
                   Check Trust Anchor Table             Lookup Issuer in Trust Store
                                │                                   │
                         ┌──────┴──────┐                     ┌──────┴──────┐
                    [In Anchor]   [Not Anchor]           [Found]      [Not Found]
                         │             │                    │              │
                         ▼             ▼                    ▼              ▼
                     Validate   Return UNTRUSTED_    Cryptographically   Return UNTRUSTED_
                     Self-Sig         ISSUER         Verify Signature         ISSUER
                         │                           against Parent
                         └──────────────┬───────────────────┘
                                        │
                                        ▼
                      [Step 3] Local Revocation Check
                                        │
                         ┌──────────────┴──────────────┐
                    [Revoked]                       [Good]
                         ▼                             ▼
                  Return REVOKED                  Return VALID
```

---

## 4. Distinct Classification Outputs
PRAMANA never lumps certificate failures into a generic error. Validation cleanly distinguishes:
- **`VALID`**: Active, unexpired, trusted anchor or valid chain to a trusted parent CA, valid cryptographic signature, and unrevoked.
- **`EXPIRED`**: Current timestamp exceeds `not_after`.
- **`NOT_YET_VALID`**: Current timestamp precedes `not_before`.
- **`UNTRUSTED_ISSUER`**: Issuer is neither registered as a trust anchor nor found in the chain database.
- **`INVALID_SIGNATURE`**: Mathematical signature verification against parent CA public key failed.
- **`REVOKED`**: Certificate appears in a synchronized CRL or marked revoked in the trust registry.
- **`INVALID_FORMAT`**: Malformed PEM or invalid ASN.1 structure.

