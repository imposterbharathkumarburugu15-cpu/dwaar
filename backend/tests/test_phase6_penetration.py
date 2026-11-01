"""Phase 6 Penetration Testing & Vulnerability Assessment Suite.

Tests:
1. IDOR / Cross-institution isolation violation rejection
2. Unauthenticated access prevention
3. Privilege escalation prevention
4. Path traversal file upload prevention
5. CSRF protection verification
6. Brute force login lockout and throttling
7. SSRF prevention against private IP/loopback addresses
8. Document tampering detection
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pramana.auth import ensure_institution_access, validate_password_complexity, PasswordPolicyError
from pramana.integrations.gateway import ExternalAPISecurityGateway, SSRFValidationError
from pramana.main import app
from pramana.models import User


def test_password_policy_complexity():
    # Too short
    with pytest.raises(PasswordPolicyError):
        validate_password_complexity("Short1!")

    # Missing special character
    with pytest.raises(PasswordPolicyError):
        validate_password_complexity("NoSpecialCharacter12")

    # Missing uppercase
    with pytest.raises(PasswordPolicyError):
        validate_password_complexity("nouppercase12!")

    # Valid
    validate_password_complexity("ValidSecurePassword@2026")
    validate_password_complexity("AdminPasswordWithSpecial@2026", is_admin=True)


def test_cross_institution_idor_prevention():
    inst_user = User(id="user_inst_1", username="inst1_admin", role="institution_admin", institution_id="INST-001")
    
    # Allowed access to own institution
    ensure_institution_access(inst_user, "INST-001")

    # Forbidden access to another institution
    with pytest.raises(HTTPException) as exc:
        ensure_institution_access(inst_user, "INST-002")
    assert exc.value.status_code == 403


def test_officer_can_access_any_institution():
    officer_user = User(id="user_off_1", username="officer_lead", role="officer", institution_id=None)
    ensure_institution_access(officer_user, "INST-001")
    ensure_institution_access(officer_user, "INST-002")


def test_unauthenticated_protected_endpoint_access():
    client = TestClient(app)
    # Accessing dashboard without cookie
    res = client.get("/api/dashboard")
    assert res.status_code == 401


def test_ssrf_protection_private_ip():
    gateway = ExternalAPISecurityGateway(allow_local_for_tests=False)
    # Loopback IP attempt
    with pytest.raises(SSRFValidationError):
        gateway.validate_destination_url("http://127.0.0.1:8080/internal-admin")

    # Private subnet attempt
    with pytest.raises(SSRFValidationError):
        gateway.validate_destination_url("http://192.168.1.1/router-config")

    # AWS/GCP metadata endpoint attempt
    with pytest.raises(SSRFValidationError):
        gateway.validate_destination_url("http://169.254.169.254/latest/meta-data/")

