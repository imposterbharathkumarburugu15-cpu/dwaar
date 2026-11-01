"""Tests for Phase 8: Enterprise Onboarding, Multi-Environment Architecture & Deployment Readiness."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from pramana.auth import hash_password
from pramana.db import Base, SessionLocal, engine, init_db
from pramana.main import app
from pramana.models import Institution, User


@pytest.fixture(autouse=True)
def setup_enterprise_db():
    init_db()
    with SessionLocal() as db:
        admin_user = db.scalars(select(User).where(User.username == "admin")).first()
        if not admin_user:
            admin_user = User(
                username="admin",
                role="admin",
                password_hash=hash_password("Pramana@2026"),
                active=True,
                display_name="Platform Administrator",
            )
            db.add(admin_user)
            db.commit()
    yield


@pytest.fixture
def auth_admin_client():
    client = TestClient(app)
    # Log in as admin
    r = client.post("/api/auth/login", json={"username": "admin", "password": "Pramana@2026"})
    assert r.status_code == 200
    client.headers["x-csrf-token"] = r.json()["csrf_token"]
    return client


def test_enterprise_institution_onboarding(auth_admin_client):
    onboard_payload = {
        "name": "Delhi Institute of Advanced Robotics",
        "aicte_id": "1-9988776655",
        "state": "Delhi",
        "category": "Engineering & Technology",
        "contact_email": "admin@diar.edu.in",
        "admin_username": "diar_admin_2026",
        "admin_password": "DiarSecurePassword@2026",
    }

    resp = auth_admin_client.post("/api/admin/institutions/onboard", json=onboard_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ONBOARDED"
    assert data["aicte_id"] == "1-9988776655"
    assert data["admin_username"] == "diar_admin_2026"

    # Verify DB persistence
    with SessionLocal() as db:
        inst = db.scalars(select(Institution).where(Institution.aicte_id == "1-9988776655")).first()
        assert inst is not None
        assert inst.name == "Delhi Institute of Advanced Robotics"

        admin_u = db.scalars(select(User).where(User.username == "diar_admin_2026")).first()
        assert admin_u is not None
        assert admin_u.role == "institution_admin"
        assert admin_u.institution_id == inst.id


def test_onboarding_rejects_duplicate_aicte_id(auth_admin_client):
    payload = {
        "name": "Duplicate College",
        "aicte_id": "1-9988776655",  # Already onboarded in previous test
        "state": "Delhi",
        "contact_email": "dup@edu.in",
        "admin_username": "dup_admin",
        "admin_password": "SecurePassword@2026",
    }
    resp = auth_admin_client.post("/api/admin/institutions/onboard", json=payload)
    assert resp.status_code == 409
    assert "already registered" in resp.text


def test_onboarding_rejects_weak_password(auth_admin_client):
    payload = {
        "name": "Weak Pass College",
        "aicte_id": "1-1122334455",
        "state": "Haryana",
        "contact_email": "weak@edu.in",
        "admin_username": "weak_admin",
        "admin_password": "short",  # Violates complexity policy
    }
    resp = auth_admin_client.post("/api/admin/institutions/onboard", json=payload)
    assert resp.status_code == 400
    assert "at least 12 characters" in resp.text
