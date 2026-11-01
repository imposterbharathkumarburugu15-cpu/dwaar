"""Unit tests for Object Storage Abstraction, Checksums, and Signed URLs (Module 5)."""

import hashlib
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pramana.db import Base, get_db
from pramana.distributed.storage import LocalStorageAdapter, S3StorageAdapter
from pramana.main import app


@pytest.fixture(autouse=True)
def setup_storage_test_db(tmp_path):
    db_file = tmp_path / "test_storage.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)

    def override_get_db():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    engine.dispose()


def test_local_storage_put_get_checksum(tmp_path):
    storage = LocalStorageAdapter(base_dir=tmp_path / "objects")
    payload = b"Federated Land Registration Certificate Document"
    key = "docs/INST-1/land_cert.pdf"

    rec = storage.upload(
        file_bytes=payload,
        object_key=key,
        original_filename="land_cert.pdf",
        content_type="application/pdf",
        institution_id="INST-1",
        uploaded_by="tester",
    )
    assert rec.object_key == key
    assert rec.byte_size == len(payload)
    assert rec.sha256_checksum == hashlib.sha256(payload).hexdigest()

    # Retrieve object
    retrieved = storage.download(key, institution_id="INST-1")
    assert retrieved == payload

    # Signed URL generation
    signed_url = storage.generate_signed_url(key, expires_in_seconds=300)
    assert "/api/v1/storage/documents/" in signed_url
    assert "expires=" in signed_url
    assert "token=" in signed_url


def test_path_traversal_defense(tmp_path):
    storage = LocalStorageAdapter(base_dir=tmp_path / "objects")
    with pytest.raises(PermissionError, match="Path traversal attempt"):
        storage.upload(
            file_bytes=b"bad content",
            object_key="../../../etc/passwd",
            original_filename="passwd",
            content_type="application/pdf",
            institution_id="INST-1",
        )

    with pytest.raises(PermissionError, match="Path traversal attempt"):
        storage.download("..\\..\\windows\\win.ini")


def test_corrupted_object_checksum_verification(tmp_path):
    storage = LocalStorageAdapter(base_dir=tmp_path / "objects")
    key = "certs/valid.pdf"
    storage.upload(
        file_bytes=b"%PDF-1.4\nunmodified_content",
        object_key=key,
        original_filename="valid.pdf",
        content_type="application/pdf",
        institution_id="INST-1",
    )

    # Manually tamper with the file on disk
    target_path = tmp_path / "objects" / "certs" / "valid.pdf"
    target_path.write_bytes(b"%PDF-1.4\ntampered_content")

    with pytest.raises(IOError, match="Cryptographic integrity violation"):
        storage.download(key, institution_id="INST-1")


def test_s3_storage_adapter_unattached_diagnostics():
    s3 = S3StorageAdapter(bucket_name="pramana-archive")
    diag = s3.health_check()
    assert diag["provider"] == "S3_OBJECT_STORAGE"
    assert diag["status"] == "NOT_CONFIGURED"
    assert diag["is_connected"] is False

