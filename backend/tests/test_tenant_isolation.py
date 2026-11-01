"""Unit & Integration tests for Multi-Tenant Data Isolation (Module 8)."""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from pramana.auth import hash_password
from pramana.db import Base, get_db
from pramana.main import app
from pramana.models import Application, Institution, User


@pytest.fixture(autouse=True)
def setup_tenant_test_db(tmp_path):
    db_file = tmp_path / "test_tenant.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)

    def override_get_db():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db
    yield engine
    app.dependency_overrides.clear()
    engine.dispose()


def test_tenant_cross_institution_isolation(setup_tenant_test_db):
    engine = setup_tenant_test_db
    client = TestClient(app)

    # Setup two distinct institutions and their admins
    inst1 = Institution(id="INST-TENANT-A", aicte_id="1-TEN-A", name="College A")
    inst2 = Institution(id="INST-TENANT-B", aicte_id="1-TEN-B", name="College B")

    admin_a = User(
        id="u-ten-a",
        username="admin_a",
        role="institution_admin",
        institution_id="INST-TENANT-A",
        display_name="Admin A",
        password_hash=hash_password("PassA@123"),
    )
    admin_b = User(
        id="u-ten-b",
        username="admin_b",
        role="institution_admin",
        institution_id="INST-TENANT-B",
        display_name="Admin B",
        password_hash=hash_password("PassB@123"),
    )

    app_a = Application(
        id="APP-TENANT-A",
        institution_id="INST-TENANT-A",
        category="Engineering",
        academic_year="2026-27",
    )
    app_b = Application(
        id="APP-TENANT-B",
        institution_id="INST-TENANT-B",
        category="Pharmacy",
        academic_year="2026-27",
    )

    with Session(engine) as s:
        s.add_all([inst1, inst2, admin_a, admin_b, app_a, app_b])
        s.commit()

    # Login as Admin A
    r_login = client.post("/api/auth/login", json={"username": "admin_a", "password": "PassA@123"})
    assert r_login.status_code == 200
    csrf = r_login.json().get("csrf_token")
    headers = {"x-csrf-token": csrf} if csrf else {}

    # Admin A attempts to process Application A (Permitted)
    r_own = client.post("/api/v1/applications/APP-TENANT-A/process", headers=headers, json={"priority": "high"})
    assert r_own.status_code == 200
    assert r_own.json()["status"] == "DISPATCHED"

    # Admin A attempts to process Application B (Denied: 403 Forbidden)
    r_other = client.post("/api/v1/applications/APP-TENANT-B/process", headers=headers, json={"priority": "high"})
    assert r_other.status_code == 403
    assert "belongs to another institution" in r_other.json()["detail"]


def test_tenant_storage_access_isolation(setup_tenant_test_db):
    engine = setup_tenant_test_db
    client = TestClient(app)

    # Setup admin
    admin_a = User(
        id="u-ten-a2",
        username="admin_a2",
        role="institution_admin",
        institution_id="INST-TENANT-A",
        display_name="Admin A2",
        password_hash=hash_password("PassA@123"),
    )
    with Session(engine) as s:
        s.add(admin_a)
        s.commit()

    # Login as Admin A
    r_login = client.post("/api/auth/login", json={"username": "admin_a2", "password": "PassA@123"})
    assert r_login.status_code == 200
    csrf = r_login.json().get("csrf_token")
    headers = {"x-csrf-token": csrf} if csrf else {}

    # Attempt to access another institution's document
    r_bad_download = client.get(
        "/api/v1/storage/documents/INST-TENANT-B/confidential.pdf",
        headers=headers,
    )
    assert r_bad_download.status_code in (403, 404)
