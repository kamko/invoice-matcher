"""Authentication and session helpers."""

import secrets
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import HTTPException, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from web.config import settings
from web.database.models import AppSettings, User, UserSession

SESSION_COOKIE_SALT = "invoice-matcher-session"
AUTH_FLOW_COOKIE = "invoice_matcher_auth_flow"
AUTH_FLOW_SALT = "invoice-matcher-auth-flow"
LEGACY_SETTING_KEYS = {
    "invoice_parent_folder_id",
    "invoice_parent_folder_name",
    "accountant_folder_id",
    "accountant_folder_name",
}


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key)


def _cookie_kwargs(max_age: Optional[int] = None) -> dict[str, Any]:
    return {
        "httponly": True,
        "secure": settings.session_cookie_secure,
        "samesite": "lax",
        "path": "/",
        "max_age": max_age,
    }


def sign_session_id(session_id: str) -> str:
    """Sign a session ID for cookie storage."""
    return _serializer().dumps({"sid": session_id}, salt=SESSION_COOKIE_SALT)


def unsign_session_cookie(cookie_value: str) -> Optional[str]:
    """Extract a session ID from a signed cookie."""
    try:
        data = _serializer().loads(cookie_value, salt=SESSION_COOKIE_SALT)
    except (BadSignature, SignatureExpired):
        return None
    return data.get("sid")


def set_session_cookie(response: Response, session_id: str) -> None:
    """Attach the signed session cookie to the response."""
    response.set_cookie(
        settings.session_cookie_name,
        sign_session_id(session_id),
        **_cookie_kwargs(max_age=settings.session_ttl_hours * 3600),
    )


def clear_session_cookie(response: Response) -> None:
    """Clear the session cookie."""
    response.delete_cookie(settings.session_cookie_name, path="/")


def set_temporary_flow_cookie(response: Response, name: str, salt: str, payload: dict[str, Any]) -> None:
    """Store a short-lived signed payload in a secure cookie."""
    signed = _serializer().dumps(payload, salt=salt)
    response.set_cookie(
        name,
        signed,
        **_cookie_kwargs(max_age=settings.temporary_flow_ttl_seconds),
    )


def load_temporary_flow_cookie(request: Request, name: str, salt: str) -> dict[str, Any]:
    """Load a signed short-lived flow payload from a cookie."""
    value = request.cookies.get(name)
    if not value:
        raise HTTPException(status_code=400, detail="Authentication flow expired. Please try again.")

    try:
        return _serializer().loads(
            value,
            salt=salt,
            max_age=settings.temporary_flow_ttl_seconds,
        )
    except SignatureExpired as exc:
        raise HTTPException(status_code=400, detail="Authentication flow expired. Please try again.") from exc
    except BadSignature as exc:
        raise HTTPException(status_code=400, detail="Invalid authentication flow state.") from exc


def clear_temporary_flow_cookie(response: Response, name: str) -> None:
    """Clear a short-lived flow cookie."""
    response.delete_cookie(name, path="/")


def ensure_user_allowed(email: str) -> None:
    """Validate the authenticated user's email against deployment rules."""
    normalized = email.strip().lower()
    allowed_emails = settings.allowed_emails
    allowed_domains = settings.allowed_domains

    if not allowed_emails and not allowed_domains:
        return

    if normalized in allowed_emails:
        return

    domain = normalized.split("@")[-1]
    if domain in allowed_domains:
        return

    raise HTTPException(status_code=403, detail="This Google account is not allowed to access the app.")


def create_session(db: Session, user: User, request: Request) -> UserSession:
    """Create a new server-side session for the user."""
    now = datetime.utcnow()
    session = UserSession(
        session_id=secrets.token_urlsafe(32),
        user_id=user.id,
        csrf_token=secrets.token_urlsafe(24),
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
        created_at=now,
        last_seen_at=now,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
        data={},
    )
    user.last_login_at = now
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_session_from_request(db: Session, request: Request) -> Optional[UserSession]:
    """Resolve the current session from the request cookie."""
    cookie_value = request.cookies.get(settings.session_cookie_name)
    if not cookie_value:
        return None

    session_id = unsign_session_cookie(cookie_value)
    if not session_id:
        return None

    session = db.query(UserSession).filter(UserSession.session_id == session_id).first()
    if not session:
        return None

    if session.expires_at <= datetime.utcnow():
        db.delete(session)
        db.commit()
        return None

    return session


def touch_session(db: Session, session: UserSession) -> None:
    """Refresh session activity timestamps."""
    session.last_seen_at = datetime.utcnow()
    session.expires_at = datetime.utcnow() + timedelta(hours=settings.session_ttl_hours)
    db.commit()


def destroy_session(db: Session, session: Optional[UserSession]) -> None:
    """Delete a session if present."""
    if not session:
        return
    db.delete(session)
    db.commit()


def get_current_user(request: Request) -> User:
    """Dependency helper to fetch the authenticated user from request state."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def get_current_session(request: Request) -> UserSession:
    """Dependency helper to fetch the authenticated session from request state."""
    session = getattr(request.state, "session", None)
    if not session:
        raise HTTPException(status_code=401, detail="Authentication required")
    return session


def maybe_seed_legacy_settings(db: Session, user: User) -> None:
    """Copy legacy global settings into a new user's settings once."""
    from web.database.models import UserSetting

    existing = db.query(UserSetting).filter(UserSetting.user_id == user.id).count()
    if existing:
        return

    legacy_settings = db.query(AppSettings).all()
    copied_any = False
    for item in legacy_settings:
        if item.key not in LEGACY_SETTING_KEYS:
            continue
        db.add(UserSetting(user_id=user.id, key=item.key, value=item.value))
        copied_any = True

    if copied_any:
        db.commit()
