# Operations Runbook

## Routine Operational Tasks
1. **Health Verification**:
   - Query `/api/v1/health` for general API health.
   - Query `/api/v1/metrics` for Prometheus operational metrics.
2. **Disaster Recovery Backup**:
   - Run snapshot backup script: `python -m pramana.distributed.backup_recovery create_snapshot`.
3. **Audit Ledger Verification**:
   - Execute verification endpoint: `GET /api/audit/verify`.
   - Confirm hash-chain continuity from genesis block to current head.
4. **Emergency Key Rotation**:
   - Invoke `POST /api/v1/trust/keys/rotate` with Super Admin authorization.

