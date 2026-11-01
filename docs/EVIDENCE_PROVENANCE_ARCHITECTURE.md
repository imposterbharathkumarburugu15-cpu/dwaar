# Evidence Provenance Architecture

## Cryptographic Lineage Tracking
Every piece of evidence processed by PRAMANA maintains a verifiable lineage:
1. `raw_input_hash`: Computed at point of receipt.
2. `extracted_facts_hash`: Canonical JSON digest of structured facts.
3. `external_verification_hash`: Hash of the raw signed government response payload.
4. `audit_merkle_checkpoint`: Signed with officer's Ed25519 key at review time.

