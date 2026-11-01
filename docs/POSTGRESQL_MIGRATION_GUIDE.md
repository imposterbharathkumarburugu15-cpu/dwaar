# PostgreSQL Migration & Production Guide

## Purpose & Overview

The PRAMANA Database Migration Engine (`pramana.distributed.db_migration`) provides a zero-data-loss, dependency-aware migration pipeline to transition from development SQLite databases to enterprise PostgreSQL clusters.

## Topological Table Order

To respect all foreign key dependencies and prevent constraint violations, tables are migrated in strict topological order:

1. `institutions`
2. `users`
3. `applications`
4. `documents`
5. `declarations`
6. `runs`
7. `findings`
8. `verifications`
9. `reviews`
10. `audits`
11. `checkpoints`
12. `auth_sessions`
13. `field_inspection_cases`
14. `field_evidences`
15. `field_inspection_reports`
16. `offline_sync_events`
17. `cryptographic_keys`
18. `key_rotation_events`
19. `certificate_records`
20. `crl_records`
21. `trust_store_entries`
22. `security_incidents`
23. `task_execution_records`
24. `document_pipeline_stages`
25. `storage_objects`

## Migration Engine CLI & Usage

```bash
# Dry run migration (inspects tables and verifies counts without writing)
python -m pramana.distributed.db_migration --source sqlite:///var/pramana.db --target postgresql://user:pass@localhost:5432/pramana --dry-run

# Execute full migration with 500-record batch chunking
python -m pramana.distributed.db_migration --source sqlite:///var/pramana.db --target postgresql://user:pass@localhost:5432/pramana --batch-size 500

# Validate data counts and integrity
python -m pramana.distributed.db_migration --source sqlite:///var/pramana.db --target postgresql://user:pass@localhost:5432/pramana --validate-only
```

## Connection Pool Tuning

For PostgreSQL deployments, `pramana/db.py` configures connection pooling:
- `pool_size`: 20 connections per API worker.
- `max_overflow`: 10 burst connections.
- `pool_timeout`: 30 seconds.
- `pool_recycle`: 1800 seconds (30 minutes).
- `pool_pre_ping`: `True` (automatic detection of dropped connections).

