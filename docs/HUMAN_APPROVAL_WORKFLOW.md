# Human Approval & Governance Workflow

## Non-Autonomous Design Mandate
Under no circumstances may an automated AI system modify or deploy compliance rules into active evaluation without verified human administrator authorization.

## Separation of Duties
- **Subject Matter Expert (SME)**: Evaluates pedagogical and legal viability; records `EXPERT_REVIEW`.
- **Competent Administrator (AICTE Member Secretary / Super Admin)**: Executes final approval and triggers `RULE_ACTIVATED`.
- **Audit Ledger Commitment**: Every state change records an immutable event in the SHA-256 Merkle tree.

