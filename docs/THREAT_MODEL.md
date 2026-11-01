# PRAMANA STRIDE Threat Model

## Threat Actors
1. **Malicious Institutional Applicant**: Attempts to forge faculty credentials, land affidavits, or fire NOCs to obtain fraudulent AICTE approval.
2. **Compromised Officer Account**: Rogue user attempting to tamper with decision records or audit trails.
3. **External Attacker**: Probes for IDOR, SSRF, injection, or DoS vulnerabilities.
4. **Insider / Infrastructure Operator**: Attempts direct database tampering.

## STRIDE Analysis

| STRIDE Category | Threat Scenario | Primary Mitigation |
|---|---|---|
| **Spoofing** | Forged digital signature on Land Affidavit | Ed25519 / RSA X.509 verification against CCA trust anchors |
| **Tampering** | Direct database modification of approval outcome | SHA-256 Merkle audit trail with Ed25519 signed checkpoints |
| **Repudiation** | Scrutiny officer denying having made an approval decision | Cryptographic signing of scrutiny decisions with private keys |
| **Information Disclosure** | Cross-institution application snooping (IDOR) | Enforced tenant isolation in `auth.py` |
| **Denial of Service** | Flooding external API endpoints or upload pipeline | Redis token-bucket rate limiting + 25MB payload caps |
| **Elevation of Privilege** | Applicant invoking officer decision endpoints | Explicit role-based access control (`require_roles`) |

