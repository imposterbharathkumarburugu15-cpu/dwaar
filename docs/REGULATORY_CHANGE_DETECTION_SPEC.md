# Regulatory Change Detection Specification

## 1. Approved Sources
Monitoring is strictly limited to verified official domains:
- `aicte-india.org/aphandbook`: Approval Process Handbook updates.
- `egazette.gov.in`: Statutory notifications and amendments to AICTE Act 1987.
- `ugc.ac.in`: Central university recognition guidelines.

## 2. Diff Computation Engine
- **Text Normalization**: Strips decorative typography and formatting differences.
- **Clause Alignment**: Uses clause identifiers (e.g. `4.1`, `4.2.1`) to match historical versions.
- **Diff Categorization**:
  - `ADDED`: Brand new regulatory requirements.
  - `MODIFIED`: Alteration of thresholds or evidence mandates.
  - `REPEALED`: Sunsetting of previous conditions.

