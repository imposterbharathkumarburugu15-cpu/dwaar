"""Server-side sessions in httpOnly cookies, role checks and object-level access control."""

import hashlib
import secrets
from datetime import UTC, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Application, AuthSession, User, utcnow

COOKIE = "pramana_session"
CSRF_HEADER = "x-csrf-token"


def cookie_name() -> str:
    # Over HTTPS the __Host- prefix makes browsers insist on Secure, Path=/ and no Domain attribute
    return f"__Host-{COOKIE}" if get_settings().cookie_secure else COOKIE

ROLES = {
    "super_admin": "Platform Super Admin",
    "aicte_admin": "AICTE Administrator",
    "regional_officer": "Regional Regulatory Officer",
    "institution_admin": "Institution Administrator",
    "institution_operator": "Institution Data Operator",
    "applicant": "Applicant",
    "external_verifier": "External Verifier",
    # Legacy aliases
    "officer": "AICTE scrutiny officer",
    "verifier": "Verification cell",
    "admin": "Administrator / auditor",
    "institution": "Institution applicant",
}

OFFICIAL_ROLES = {
    "super_admin",
    "aicte_admin",
    "regional_officer",
    "officer",
    "external_verifier",
    "verifier",
    "admin",
}
INSTITUTION_ROLES = {"institution_admin", "institution_operator", "institution", "applicant"}

# Action-level permissions matrix for granular RBAC
PERMISSIONS: dict[str, set[str]] = {
    "platform:view": {"super_admin", "admin"},
    "platform:configure": {"super_admin"},
    "users:manage": {"super_admin", "aicte_admin"},
    "keys:rotate": {"super_admin"},
    "audit:view": {"super_admin", "aicte_admin", "regional_officer", "officer", "admin"},
    "audit:checkpoint": {"super_admin", "aicte_admin", "admin"},
    "audit:simulate_tamper": {"super_admin", "aicte_admin", "admin"},
    "rules:view": {"super_admin", "aicte_admin", "regional_officer", "officer", "external_verifier", "verifier", "institution_admin"},
    "rules:simulate": {"super_admin", "aicte_admin", "regional_officer", "officer"},
    "rules:configure": {"super_admin", "aicte_admin"},
    "apps:list_all": {"super_admin", "aicte_admin", "regional_officer", "officer", "admin"},
    "apps:view_assigned": {"regional_officer", "officer", "external_verifier", "verifier"},
    "apps:view_own": {"institution_admin", "institution_operator", "institution", "applicant"},
    "apps:create": {"institution_admin", "institution_operator", "institution"},
    "apps:upload_docs": {"institution_admin", "institution_operator", "institution"},
    "apps:submit": {"institution_admin", "institution"},
    "apps:scrutinize": {"super_admin", "aicte_admin", "regional_officer", "officer"},
    "apps:review_action": {"regional_officer", "officer", "aicte_admin"},
    "apps:request_rectification": {"regional_officer", "officer", "aicte_admin"},
    "apps:respond_rectification": {"institution_admin", "institution_operator", "institution"},
    "apps:record_decision": {"aicte_admin", "regional_officer", "officer"},
    "risk:view_sector": {"super_admin", "aicte_admin", "regional_officer", "officer"},
    "forensics:analyze": {"super_admin", "aicte_admin", "regional_officer", "officer", "external_verifier", "verifier"},
    "offline:export_bundle": {"super_admin", "aicte_admin", "regional_officer", "officer", "external_verifier"},
    "offline:sync": {"super_admin", "aicte_admin", "regional_officer", "officer", "external_verifier"},
    "offline:reconcile": {"super_admin", "aicte_admin", "regional_officer", "officer"},
    "inspection:create": {"super_admin", "aicte_admin", "regional_officer", "officer"},
    "inspection:sign": {"super_admin", "aicte_admin", "regional_officer", "officer"},
    "inspection:view": {"super_admin", "aicte_admin", "regional_officer", "officer", "external_verifier", "verifier"},
}

_ph = PasswordHasher()


class PasswordPolicyError(ValueError):
    """Raised when password fails complexity or length requirements."""
    pass


def validate_password_complexity(pw: str, is_admin: bool = False) -> None:
    """Enforces enterprise password complexity rules."""
    min_len = 12 if is_admin else 8
    if len(pw) < min_len:
        raise PasswordPolicyError(f"Password must be at least {min_len} characters long.")
    if not any(c.isupper() for c in pw):
        raise PasswordPolicyError("Password must include at least one uppercase letter.")
    if not any(c.islower() for c in pw):
        raise PasswordPolicyError("Password must include at least one lowercase letter.")
    if not any(c.isdigit() for c in pw):
        raise PasswordPolicyError("Password must include at least one digit.")
    if not any(c in "!@#$%^&*()-_=+[]{}|;:,.<>?" for c in pw):
        raise PasswordPolicyError("Password must include at least one special character.")


def ensure_institution_access(user: User, institution_id: str | None) -> None:
    """Enforces multi-institution isolation. Prevents IDOR cross-institution access."""
    if user.role in OFFICIAL_ROLES:
        return  # Regulatory officers can view applications across institutions
    if not user.institution_id or not institution_id or user.institution_id != institution_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Access denied: You do not have permission to view or modify records from another institution.",
        )


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def check_password(stored: str, pw: str) -> bool:
    try:
        return _ph.verify(stored, pw)
    except VerifyMismatchError:
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(db: Session, user: User, response: Response) -> AuthSession:
    token = secrets.token_urlsafe(32)
    s = get_settings()
    sess = AuthSession(
        token_hash=_token_hash(token),
        user_id=user.id,
        csrf_token=secrets.token_urlsafe(24),
        expires_at=utcnow() + timedelta(minutes=s.session_ttl_minutes),
    )
    db.add(sess)
    response.set_cookie(
        cookie_name(), token, httponly=True, samesite="strict", secure=s.cookie_secure, path="/",
        max_age=s.session_ttl_minutes * 60
    )
    return sess


def end_session(db: Session, request: Request, response: Response) -> None:
    token = request.cookies.get(cookie_name())
    if token:
        sess = db.get(AuthSession, _token_hash(token))
        if sess:
            db.delete(sess)
    response.delete_cookie(cookie_name(), path="/", secure=get_settings().cookie_secure, httponly=True,
                           samesite="strict")


def current_session(request: Request, db: Session = Depends(get_db)) -> AuthSession:
    token = request.cookies.get(cookie_name())
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not signed in")
    sess = db.get(AuthSession, _token_hash(token))
    if not sess:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired")
    exp = sess.expires_at if sess.expires_at.tzinfo else sess.expires_at.replace(tzinfo=UTC)
    if exp < utcnow():
        db.delete(sess)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired")
    # Unsafe methods must echo the CSRF token, which a cross-site page cannot read
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        sent = request.headers.get(CSRF_HEADER, "")
        if not secrets.compare_digest(sent, sess.csrf_token):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "missing or invalid CSRF token")
    return sess


def current_user(sess: AuthSession = Depends(current_session), db: Session = Depends(get_db)) -> User:
    user = db.get(User, sess.user_id)
    if not user or not user.active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account disabled")
    return user


def require_roles(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        # Check direct role or role aliases
        if user.role not in roles:
            # Map legacy officer -> regional_officer, admin -> super_admin, institution -> institution_operator
            role_aliases = {
                "officer": {"regional_officer", "aicte_admin", "super_admin"},
                "verifier": {"external_verifier"},
                "admin": {"super_admin", "aicte_admin"},
                "institution": {"institution_admin", "institution_operator", "applicant"},
            }
            allowed = False
            for req in roles:
                if user.role in role_aliases.get(req, set()):
                    allowed = True
                    break
            if not allowed:
                raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires role: {', '.join(roles)}")
        return user

    return dep


def has_permission(user: User, perm: str) -> bool:
    allowed_roles = PERMISSIONS.get(perm, set())
    if user.role in allowed_roles:
        return True
    # Check aliases
    alias_map = {
        "super_admin": {"admin"},
        "regional_officer": {"officer"},
        "institution_operator": {"institution"},
        "external_verifier": {"verifier"},
    }
    for r in allowed_roles:
        if user.role in alias_map.get(r, set()):
            return True
    return False


def require_permission(perm: str):
    def dep(user: User = Depends(current_user)) -> User:
        if not has_permission(user, perm):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"insufficient permissions: requires '{perm}'")
        return user

    return dep


def can_access_application(user: User, app: Application) -> bool:
    if user.role in OFFICIAL_ROLES:
        return True
    return user.role in INSTITUTION_ROLES and user.institution_id == app.institution_id


def load_application(db: Session, user: User, app_id: str) -> Application:
    """Fetch an application with object-level authorization; institutions only see their own."""
    app = db.get(Application, app_id)
    if not app or not can_access_application(user, app):
        # 404 rather than 403 so other institutions' application IDs are not confirmed to exist
        raise HTTPException(status.HTTP_404_NOT_FOUND, "application not found")
    return app
