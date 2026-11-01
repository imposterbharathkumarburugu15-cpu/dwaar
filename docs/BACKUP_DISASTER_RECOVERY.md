# Backup & Disaster Recovery Orchestration

## Disaster Recovery Objectives

- **Recovery Point Objective (RPO):** < 15 minutes (hourly full snapshots + continuous WAL write-ahead logging).
- **Recovery Time Objective (RTO):** < 10 minutes (automated container volume recovery and state restoration).

## Snapshot Archive Structure

Every automated snapshot created by `pramana.distributed.backup_recovery.DisasterRecoveryOrchestrator` produces an auditable archive:

```
backups/
└── prm_backup_20261101_153000/
    ├── database.sqlite / pg_dump.sql
    ├── keys/
    │   ├── prm_audit_signing_v1.key
    │   └── prm_offline_signing_v1.key
    └── manifest.json
```

## Manifest Tamper-Proof Verification

The `manifest.json` file contains:
- SHA-256 cryptographic digests of every backed-up file.
- Row counts of every database table at snapshot time.
- SHA-256 integrity hash of the manifest dictionary itself.

During recovery, `verify_backup_integrity()` recalculates file checksums against the manifest. If any file has been modified or corrupted on disk, restoration aborts immediately with an audit security alert.

