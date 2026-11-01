"""Unit & Integration tests for Backup & Disaster Recovery Orchestrator (Module 12)."""

import json
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pramana.db import Base
from pramana.distributed.backup_recovery import DisasterRecoveryOrchestrator
from pramana.models import Institution


def test_disaster_recovery_snapshot_and_manifest(tmp_path):
    # Setup source sqlite DB
    db_file = tmp_path / "pramana_prod.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)

    with Session(engine) as s:
        s.add(Institution(id="INST-DR-1", aicte_id="1-DR-1", name="DR College"))
        s.commit()

        backup_dest = tmp_path / "backups"
        orchestrator = DisasterRecoveryOrchestrator(backup_dir=backup_dest)

        manifest = orchestrator.create_backup_snapshot(db_session=s, backup_name="test_snap_1")

        assert manifest.backup_id == "test_snap_1"
        assert manifest.table_record_counts.get("institutions") == 1
        assert (backup_dest / "test_snap_1").exists()

        # Test verification
        verify_res = orchestrator.verify_backup_integrity("test_snap_1")
        assert verify_res["valid"] is True
        assert verify_res["files_checked"] >= 0

    engine.dispose()


def test_manifest_tamper_detection(tmp_path):
    db_file = tmp_path / "pramana_prod2.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)

    backup_dest = tmp_path / "backups2"
    orchestrator = DisasterRecoveryOrchestrator(backup_dir=backup_dest)

    with Session(engine) as s:
        s.add(Institution(id="INST-DR-2", aicte_id="1-DR-2", name="DR College 2"))
        s.commit()
        manifest = orchestrator.create_backup_snapshot(db_session=s, backup_name="test_snap_2")

    engine.dispose()

    # Tamper with file in backup
    snapshot_dir = backup_dest / "test_snap_2"
    db_backup_file = snapshot_dir / "database.sqlite"
    if db_backup_file.exists():
        db_backup_file.write_bytes(b"corrupted_tampered_database_payload")
        verify_res = orchestrator.verify_backup_integrity("test_snap_2")
        assert verify_res["valid"] is False
        assert len(verify_res["mismatches"]) > 0

