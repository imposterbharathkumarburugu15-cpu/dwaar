# Enterprise Institution Onboarding Guide

## Workflow Overview
1. **Onboarding Initiation**: Regulatory administrator submits institution details via `POST /api/admin/institutions/onboard`.
2. **AICTE ID Uniqueness Verification**: System ensures the permanent AICTE identifier has not been previously claimed.
3. **Administrator Provisioning**: Provisions an `institution_admin` account with enforced enterprise password complexity (min 12 chars, upper, lower, digit, symbol).
4. **Tenant Isolation Binding**: All subsequent documents and applications are isolated to the institution's scope.
5. **Auditable Checkpoint**: An immutable `enterprise.institution_onboarded` audit event is recorded in the Merkle log.

