"""Unit & Integration tests for Distributed 12-Stage Document Processing Pipeline (Module 4)."""

import base64
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pramana.db import Base, get_db
from pramana.distributed.pipeline import (
    DistributedDocumentPipeline,
    PIPELINE_STAGES,
    default_document_pipeline,
)
from pramana.distributed.models import DocumentPipelineStageRecord
from pramana.distributed.tasks import get_task_db
from pramana.main import app


@pytest.fixture(autouse=True)
def setup_pipeline_test_db(tmp_path):
    db_file = tmp_path / "test_pipeline.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)

    def override_get_db():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    engine.dispose()


def test_12_stages_completeness():
    assert len(PIPELINE_STAGES) == 12
    assert PIPELINE_STAGES[0] == "DOCUMENT_UPLOADED"
    assert PIPELINE_STAGES[-1] == "FINAL_SCRUTINY_RESULT"


def test_chunked_streaming_hashing(tmp_path):
    pipeline = DistributedDocumentPipeline()
    test_file = tmp_path / "sample.pdf"
    content = b"%PDF-1.4\nTest Document Content For Chunked Streaming Verification\n%%EOF"
    test_file.write_bytes(content)

    h = pipeline.stream_compute_sha256(test_file, chunk_size=16)
    import hashlib
    expected_h = hashlib.sha256(content).hexdigest()
    assert h == expected_h


def test_pipeline_execution_all_stages():
    pipeline = default_document_pipeline
    sample_bytes = b"%PDF-1.4\nSample Land Affidavit\n%%EOF"
    b64_data = base64.b64encode(sample_bytes).decode("utf-8")

    res = pipeline.execute_pipeline(
        document_id="DOC-PIPE-001",
        application_id="APP-PIPE-001",
        institution_id="INST-PIPE-001",
        file_bytes_b64=b64_data,
    )

    assert res["status"] == "COMPLETED"
    assert res["stages_executed"] == 12
    assert "stages_completed" in res
    assert len(res["stages_completed"]) == 12

    # Verify audit stages in database
    with get_task_db() as s:
        db_stages = s.query(DocumentPipelineStageRecord).filter_by(document_id="DOC-PIPE-001").all()
        assert len(db_stages) == 12
        for stg in db_stages:
            assert stg.status == "COMPLETED"
            assert stg.stage_name in PIPELINE_STAGES
