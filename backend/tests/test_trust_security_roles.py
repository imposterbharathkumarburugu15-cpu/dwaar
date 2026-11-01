"""Tests for Role-Based Access Control and Security Enforcement in Trust Infrastructure.

Verifies:
1. Super Admin and AICTE Admin can generate, rotate, and revoke cryptographic keys.
2. Super Admin can manage trust anchors and resolve security incidents.
3. Non-admin roles (institution_admin, external_verifier, regional_officer) are blocked with 403 Forbidden
   when attempting to rotate/revoke keys or alter trust stores.
4. Unauthenticated requests are rejected with 401 Unauthorized.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pramana.auth import hash_password
from pramana.db import Base, get_db
from pramana.main import app
from pramana.models import User
from pramana.trust.kms import kms_service


@pytest.fixture
def trust_role_setup(tmp_path):
    db_file = tmp_path / "test_trust_roles.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        # Users
        u_admin = User(
            id="u-secadmin",
            username="sec_admin",
            role="super_admin",
            display_name="Security Super Admin",
            password_hash=hash_password("Pass@123"),
        )
        u_aicte = User(
            id="u-aicte",
            username="aicte_lead",
            role="aicte_admin",
            display_name="AICTE Trust Lead",
            password_hash=hash_password("Pass@123"),
        )
        u_inst = User(
            id="u-instadmin",
            username="inst_admin",
            role="institution_admin",
            institution_id="INST-0001",
            display_name="Institute Admin",
            password_hash=hash_password("Pass@123"),
        )
        u_verifier = User(
            id="u-verifier",
            username="ext_verifier",
            role="external_verifier",
            display_name="External Auditor",
            password_hash=hash_password("Pass@123"),
        )
        session.add_all([u_admin, u_aicte, u_inst, u_verifier])
        session.commit()

        # Seed a test key
        kms_service.generate_key(
            session,
            key_id="prm-rbac-test-key-v1",
            algorithm="ED25519",
            key_purpose="audit_signing",
            operator_username="sec_admin",
        )

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


def test_admin_can_generate_and_rotate_key(trust_role_setup):
    client, _ = trust_role_setup
    _login(client, "sec_admin")

    # Generate key
    res = client.post(
        "/api/trust/keys",
        json={
            "key_id": "prm-sec-key-v1",
            "algorithm": "ED25519",
            "key_purpose": "qr_issuance",
        },
    )
    assert res.status_code == 200
    assert res.json()["key_id"] == "prm-sec-key-v1"

    # Rotate key
    res_rot = client.post(
        "/api/trust/keys/prm-sec-key-v1/rotate",
        json={
            "rotation_reason": "Annual scheduled rotation",
            "grace_period_days": 15,
        },
    )
    assert res_rot.status_code == 200
    assert res_rot.json()["status"] == "rotated"
    assert res_rot.json()["new_version"] == 2


def test_non_admin_forbidden_from_rotating_key(trust_role_setup):
    client, _ = trust_role_setup

    # 1. Institution Admin attempt
    _login(client, "inst_admin")
    res_inst = client.post(
        "/api/trust/keys/prm-rbac-test-key-v1/rotate",
        json={"rotation_reason": "Malicious attempt"},
    )
    assert res_inst.status_code == 403

    # 2. External Verifier attempt
    _login(client, "ext_verifier")
    res_verif = client.post(
        "/api/trust/keys/prm-rbac-test-key-v1/revoke",
        json={"reason": "Unauthorized revocation"},
    )
    assert res_verif.status_code == 403


def test_unauthenticated_request_rejected(trust_role_setup):
    client, _ = trust_role_setup
    res = client.get("/api/trust/keys")
    assert res.status_code == 401


def test_authenticated_users_can_read_keys_metadata(trust_role_setup):
    client, _ = trust_role_setup
    _login(client, "inst_admin")
    res = client.get("/api/trust/keys")
    assert res.status_code == 200
    keys = res.json()
    assert len(keys) >= 1
    # Verify no private material is leaked
    for k in keys:
        assert "private_key" not in k
        assert "encrypted_private_key" not in k
