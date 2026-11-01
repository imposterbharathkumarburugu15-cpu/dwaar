"""Unit & Integration tests for PostgreSQL Migration Tooling (Module 1)."""

from pathlib import Path
import tempfile
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pramana.db import Base
from pramana.distributed.db_migration import DatabaseMigrationEngine
from pramana.models import Institution, User, Application


@pytest.fixture
def test_migration_dbs():
    temp_dir = tempfile.mkdtemp(prefix="pramana_mig_test_")
    src_path = Path(temp_dir) / "source.db"
    dest_path = Path(temp_dir) / "target.db"

    src_url = f"sqlite:///{src_path}"
    dest_url = f"sqlite:///{dest_path}"

    src_engine = create_engine(src_url)
    dest_engine = create_engine(dest_url)

    Base.metadata.create_all(src_engine)
    Base.metadata.create_all(dest_engine)

    # Seed source database with known records
    with Session(src_engine) as session:
        inst = Institution(id="INST-MIG-1", aicte_id="1-MIG-1", name="Test Migration Institute")
        user = User(
            id="u-mig-1",
            username="mig_admin",
            role="institution_admin",
            institution_id="INST-MIG-1",
            display_name="Migration Admin",
            password_hash="testhash",
        )
        app = Application(
            id="APP-MIG-1",
            institution_id="INST-MIG-1",
            category="Engineering",
            academic_year="2026-27",
        )
        session.add_all([inst, user, app])
        session.commit()

    engine_mgr = DatabaseMigrationEngine(source_url=src_url, target_url=dest_url)
    yield engine_mgr, src_engine, dest_engine

    src_engine.dispose()
    dest_engine.dispose()


def test_migration_dry_run(test_migration_dbs):
    engine_mgr, src_engine, dest_engine = test_migration_dbs
    res = engine_mgr.execute_migration(dry_run=True)

    assert res.status == "DRY_RUN_COMPLETED"
    assert "institutions" in res.tables
    assert res.tables["institutions"].source_count == 1
    assert res.tables["users"].source_count == 1
    assert res.tables["applications"].source_count == 1

    # Verify target DB remains empty in dry run
    with Session(dest_engine) as session:
        assert session.query(Institution).count() == 0


def test_migration_execution_and_validation(test_migration_dbs):
    engine_mgr, src_engine, dest_engine = test_migration_dbs
    res = engine_mgr.execute_migration(dry_run=False, batch_size=50)

    assert res.status == "SUCCESS"
    assert res.tables["institutions"].source_count == 1
    assert res.tables["institutions"].target_count == 1
    assert res.tables["users"].source_count == 1
    assert res.tables["users"].target_count == 1
    assert res.tables["applications"].source_count == 1
    assert res.tables["applications"].target_count == 1

    # Validation check
    val = engine_mgr.execute_migration(validate_only=True)
    assert val.status == "SUCCESS"
    assert val.tables["institutions"].status == "VALIDATED"

