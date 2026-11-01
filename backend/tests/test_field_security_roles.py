"""Tests for Role-Based Access Control and Security Isolation in Field Scrutiny (Module 9).

Verifies:
1. Authorized officers can create and sign field inspections.
2. Institution users cannot create field inspection cases (403 Forbidden).
3. Institution users cannot sign field inspection cases (403 Forbidden).
4. Cross-institution data isolation: Institution A cannot access Institution B's inspections.
5. External verifier has read-only access and cannot sign or create inspections.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pramana.auth import hash_password
from pramana.db import Base, get_db
from pramana.main import app
from pramana.models import Application, Institution, User
from pramana.offline.models import FieldInspectionCase


@pytest.fixture
def test_setup(tmp_path):
    db_file = tmp_path / "test_roles.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    
    with Session(engine) as session:
        # Institutions
        inst_a = Institution(id="INST-0001", aicte_id="1-0001", name="College A")
        inst_b = Institution(id="INST-0002", aicte_id="1-0002", name="College B")
        session.add_all([inst_a, inst_b])
        
        # Applications
        app_a = Application(id="APP-001", institution_id="INST-0001", category="Engineering", academic_year="2026-27")
        app_b = Application(id="APP-002", institution_id="INST-0002", category="Management", academic_year="2026-27")
        session.add_all([app_a, app_b])
        
        # Users
        u_officer = User(id="u-officer", username="reg_officer", role="regional_officer", display_name="Regional Officer", password_hash=hash_password("Pass@123"))
        u_inst_admin = User(id="u-inst", username="inst_admin_a", role="institution_admin", institution_id="INST-0001", display_name="Admin A", password_hash=hash_password("Pass@123"))
        u_inst_b = User(id="u-inst-b", username="inst_admin_b", role="institution_admin", institution_id="INST-0002", display_name="Admin B", password_hash=hash_password("Pass@123"))
        u_verifier = User(id="u-verif", username="ext_verifier", role="external_verifier", display_name="External Verifier", password_hash=hash_password("Pass@123"))
        
        session.add_all([u_officer, u_inst_admin, u_inst_b, u_verifier])
        
        # Inspection Case for College A
        insp_a = FieldInspectionCase(
            id="insp-case-a",
            case_number="INSP-COLLEGE-A",
            application_id="APP-001",
            institution_id="INST-0001",
            assigned_officer_id="u-officer",
            status="draft",
        )
        session.add(insp_a)
        session.commit()

    def override_get_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    
    yield client, engine
    
    app.dependency_overrides.clear()


def _login(client, username, password="Pass@123"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200
    client.headers["x-csrf-token"] = r.json()["csrf_token"]
    return client


def test_officer_can_create_field_inspection(test_setup):
    """Test 1: Authorized regulatory officer can create a field inspection."""
    client, _ = test_setup
    _login(client, "reg_officer")
    
    r = client.post("/api/offline/inspections", json={
        "application_id": "APP-001",
        "case_number": "INSP-NEW-OFFICER-01",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["case_number"] == "INSP-NEW-OFFICER-01"


def test_institution_user_cannot_create_inspection(test_setup):
    """Test 2: Institution administrator is forbidden from creating field inspections."""
    client, _ = test_setup
    _login(client, "inst_admin_a")
    
    r = client.post("/api/offline/inspections", json={
        "application_id": "APP-001",
        "case_number": "INSP-FORBIDDEN-01",
    })
    assert r.status_code == 403


def test_institution_user_cannot_sign_inspection(test_setup):
    """Test 3: Institution user cannot sign an inspection report."""
    client, _ = test_setup
    _login(client, "inst_admin_a")
    
    r = client.post("/api/offline/inspections/insp-case-a/sign", json={
        "summary": "Attempted self sign",
        "recommendation": "approve",
    })
    assert r.status_code == 403


def test_cross_institution_data_isolation(test_setup):
    """Test 4: Institution B cannot view Institution A's inspection details."""
    client, _ = test_setup
    _login(client, "inst_admin_b")
    
    # Institution B requests inspection of College A
    r = client.get("/api/offline/inspections/insp-case-a")
    assert r.status_code == 403


def test_external_verifier_read_only(test_setup):
    """Test 5: External verifier cannot sign or create inspections."""
    client, _ = test_setup
    _login(client, "ext_verifier")
    
    # Cannot create
    r_create = client.post("/api/offline/inspections", json={"application_id": "APP-001", "case_number": "INSP-X"})
    assert r_create.status_code == 403
    
    # Cannot sign
    r_sign = client.post("/api/offline/inspections/insp-case-a/sign", json={"recommendation": "approve"})
    assert r_sign.status_code == 403
