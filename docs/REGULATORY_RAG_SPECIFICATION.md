# Regulatory RAG Engine & Hallucination Prevention Specification

## Architecture
The Regulatory RAG engine retrieves information strictly from codified statutory instruments:
- AICTE Act, 1987
- AICTE (Grant of Approvals for Technical Institutions) Regulations, 2020 (Amended 2021)
- AICTE Approval Process Handbook (APH) 2024–2027

## Anti-Hallucination Guardrails
1. **Verbatim Quotation**: Citations must map to exact clause numbers, page references, and statutory instruments.
2. **Missing Source Handling**: If a user query refers to non-existent or unverified requirements, the engine explicitly returns `INSUFFICIENT_REGULATORY_EVIDENCE`.
3. **No Unbacked Extrapolations**: The assistant never invents or hypothesizes regulatory rules.

