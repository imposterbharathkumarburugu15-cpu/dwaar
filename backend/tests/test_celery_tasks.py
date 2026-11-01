"""Unit & Integration tests for Celery Asynchronous Tasks, Idempotency & Retries (Module 3)."""

from pathlib import Path
import tempfile
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pramana.db import Base, get_db
from pramana.distributed.models import TaskExecutionRecord
from pramana.distributed.tasks import (
    get_task_db,
    init_task_record,
    process_document_pipeline_task,
    scrutinize_application_async_task,
    update_task_state,
)
from pramana.main import app


@pytest.fixture(autouse=True)
def setup_tasks_test_db(tmp_path):
    db_file = tmp_path / "test_tasks.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)

    def override_get_db():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    engine.dispose()


def test_task_record_initialization_and_state_tracking():
    task_id = "test_task_id_001"
    rec = init_task_record(
        task_id=task_id,
        task_name="test_pipeline",
        queue="document_processing",
        payload={"doc_id": "D1"},
        institution_id="INST-1",
        initiated_by="tester",
    )
    assert rec.task_id == task_id
    assert rec.status == "PENDING"
    assert rec.queue == "document_processing"

    # Transition to RUNNING
    update_task_state(task_id, "RUNNING")
    with get_task_db() as s:
        updated = s.get(TaskExecutionRecord, task_id)
        assert updated.status == "RUNNING"
        assert updated.started_at is not None

    # Transition to COMPLETED with result payload
    update_task_state(task_id, "COMPLETED", result={"verdict": "GENUINE"}, duration_ms=125.5)
    with get_task_db() as s:
        final = s.get(TaskExecutionRecord, task_id)
        assert final.status == "COMPLETED"
        assert final.completed_at is not None
        assert final.result_json == {"verdict": "GENUINE"}
        assert final.duration_ms == 125.5


def test_task_idempotency_skip():
    task_id = "task_D-PRE"
    # Pre-populate completed record with key task_D-PRE
    init_task_record(
        task_id=task_id,
        task_name="process_document_pipeline",
        queue="document_processing",
        payload={"document_id": "D-PRE"},
        institution_id="INST-1",
    )
    update_task_state(task_id, "COMPLETED", result={"cached_output": True})

    # Calling task for document D-PRE resolves to task_D-PRE and returns cached result
    res = process_document_pipeline_task(
        document_id="D-PRE",
        application_id="APP-PRE",
        institution_id="INST-1",
    )
    assert res == {"cached_output": True}
