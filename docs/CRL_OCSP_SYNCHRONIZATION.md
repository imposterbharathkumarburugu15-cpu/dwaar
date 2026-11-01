# PRAMANA — Dynamic CRL & OCSP Synchronization Architecture

## 1. Overview
Revocation is the critical operational defense in public key infrastructure. Modules 5 & 6 (`backend/pramana/trust/crl_ocsp.py`) provide robust Certificate Revocation List (CRL) synchronization and Online Certificate Status Protocol (OCSP) verification with active defenses against replay and rollback attacks.

---

## 2. CRL Anti-Rollback Protection Mechanism

### Threat Model:
An adversary who compromised an institutional or officer certificate obtains an older, validly-signed CRL from prior weeks (where the certificate was not yet listed as revoked). The adversary attempts to submit this older CRL to reset revocation states in the registry.

### PRAMANA Defense:
1. Every X.509 CRL contains an optional, standard extension: `CRLNumber` (OID `2.5.29.20`), an integer sequentially incremented by the issuing CA upon every CRL publication.
2. During `sync_crl()`, PRAMANA queries the database for the latest synchronized sequence number for that `issuer_dn`:
   ```sql
   SELECT MAX(crl_number) FROM crl_records WHERE issuer_dn = :iss_dn;
   ```
3. If the incoming CRL sequence number is **less than or equal to** the stored sequence number:
   ```python
   if latest_crl and incoming_crl_number <= latest_crl.crl_number:
       return CRLSyncResult(
           status="ROLLBACK_ATTEMPT",
           is_rollback=True,
           error=f"Rollback attack rejected: sequence {incoming_crl_number} <= {latest_crl.crl_number}"
       )
   ```
4. The transaction is aborted, an alert audit event (`crl.rollback_attempt_blocked`) is permanently recorded, and existing revocations remain intact.

---

## 3. Freshness & Offline Snapshot Evaluation
- **Freshness Check**: If `now > crl.next_update_utc`, PRAMANA flags the CRL status as `CRL_EXPIRED`.
- **Offline Snapshot Trust**: In offline field inspection environments where CA servers cannot be reached in real-time, cached CRL evaluation reports `GOOD_AS_OF_LAST_SYNC` rather than an unconditional `GOOD`. This informs officers that the certificate was unrevoked at the moment of the last field-kit synchronization.

---

## 4. OCSP Integration Abstraction
For real-time online verification where network connectivity is active:
1. **Request Construction**: Generates DER-encoded OCSP request targeting the leaf serial number.
2. **Response Parsing**: Parses `cryptography.x509.ocsp.load_der_ocsp_response`.
3. **Responder Signature Check**: Cryptographically verifies the signature on the OCSP response against the authorized CA / OCSP responder certificate.
4. **Status Mapping**: Accurately maps OCSP response states: `GOOD`, `REVOKED`, `UNKNOWN`, `EXPIRED_RESPONSE`, or `SIGNATURE_INVALID`.

