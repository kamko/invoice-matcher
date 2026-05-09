"""Authentication router for Google login and app sessions."""

import base64
import hashlib
import json
import secrets
import urllib.parse
import urllib.request

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from sqlalchemy.orm import Session

from web.auth import (
    AUTH_FLOW_COOKIE,
    AUTH_FLOW_SALT,
    clear_session_cookie,
    clear_temporary_flow_cookie,
    create_session,
    ensure_user_allowed,
    get_current_session,
    get_current_user,
    load_temporary_flow_cookie,
    set_session_cookie,
    set_temporary_flow_cookie,
)
from web.config import settings
from web.database import get_db
from web.database.models import GoogleDriveConnection, User
from web.schemas.auth import AuthSessionResponse, AuthUserResponse
from web.security import decrypt_json, encrypt_json
from web.services.gdrive_service import GDriveService

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _configured_app_origin() -> str:
    """Derive the public app origin from the configured auth callback."""
    parsed = urllib.parse.urlsplit(settings.google_auth_redirect_uri)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return ""


def _request_origin(request: Request) -> str:
    """Best-effort origin for popup handoff behind proxies and HTTPS terminators."""
    origin = request.headers.get("origin")
    if origin:
        return origin

    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_proto and forwarded_host:
        proto = forwarded_proto.split(",")[0].strip()
        host = forwarded_host.split(",")[0].strip()
        if proto and host:
            return f"{proto}://{host}"

    configured_origin = _configured_app_origin()
    if configured_origin:
        return configured_origin

    return request.base_url.scheme + "://" + request.base_url.netloc


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def _build_google_auth_url(state: str, nonce: str, code_challenge: str) -> str:
    scopes = [
        "openid",
        "email",
        "profile",
        *GDriveService.SCOPES,
    ]
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_auth_redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "consent select_account",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def _exchange_code_for_tokens(code: str, code_verifier: str) -> dict:
    payload = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_auth_redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Google token exchange failed: {exc}") from exc


def _store_google_drive_connection(db: Session, user: User, tokens: dict) -> None:
    refresh_token = tokens.get("refresh_token")
    connection = db.query(GoogleDriveConnection).filter(
        GoogleDriveConnection.user_id == user.id
    ).first()

    if connection and not refresh_token:
        existing_payload = decrypt_json(connection.encrypted_credentials)
        refresh_token = existing_payload.get("refresh_token")

    if not refresh_token:
        raise HTTPException(
            status_code=400,
            detail="Google login did not return a reusable Drive refresh token. Please try again.",
        )

    creds_payload = {
        "token": tokens.get("access_token"),
        "refresh_token": refresh_token,
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "scopes": GDriveService.SCOPES,
    }

    if not connection:
        connection = GoogleDriveConnection(
            user_id=user.id,
            email=user.email,
            encrypted_credentials=encrypt_json(creds_payload),
            scopes=" ".join(GDriveService.SCOPES),
        )
        db.add(connection)
    else:
        connection.email = user.email
        connection.encrypted_credentials = encrypt_json(creds_payload)
        connection.scopes = " ".join(GDriveService.SCOPES)


@router.get("/login")
def login_with_google(request: Request, popup: bool = True):
    """Start the Google OIDC login flow."""
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=503, detail="Google authentication is not configured")

    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    response = JSONResponse(
        {
            "auth_url": _build_google_auth_url(state, nonce, _code_challenge(verifier)),
        }
    )
    set_temporary_flow_cookie(
        response,
        AUTH_FLOW_COOKIE,
        AUTH_FLOW_SALT,
        {
            "state": state,
            "nonce": nonce,
            "code_verifier": verifier,
            "popup": popup,
            "origin": _request_origin(request),
        },
    )
    return response


@router.get("/callback")
def auth_callback(request: Request, code: str, state: str, db: Session = Depends(get_db)):
    """Complete the Google OIDC flow and create an app session."""
    flow = load_temporary_flow_cookie(request, AUTH_FLOW_COOKIE, AUTH_FLOW_SALT)
    if flow.get("state") != state:
        raise HTTPException(status_code=400, detail="State mismatch during Google login")

    tokens = _exchange_code_for_tokens(code, flow["code_verifier"])
    raw_id_token = tokens.get("id_token")
    if not raw_id_token:
        raise HTTPException(status_code=400, detail="Google login did not return an ID token")

    try:
        verified = id_token.verify_oauth2_token(
            raw_id_token,
            GoogleRequest(),
            settings.google_client_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid Google ID token: {exc}") from exc

    if verified.get("nonce") != flow.get("nonce"):
        raise HTTPException(status_code=400, detail="Invalid login nonce")

    email = verified.get("email")
    sub = verified.get("sub")
    if not email or not sub:
        raise HTTPException(status_code=400, detail="Google account is missing required identity fields")

    ensure_user_allowed(email)

    user = db.query(User).filter(User.google_sub == sub).first()
    if not user:
        user = User(
            google_sub=sub,
            email=email.lower(),
            full_name=verified.get("name"),
            picture_url=verified.get("picture"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.email = email.lower()
        user.full_name = verified.get("name")
        user.picture_url = verified.get("picture")
        db.commit()
        db.refresh(user)

    _store_google_drive_connection(db, user, tokens)

    from web.auth import maybe_seed_legacy_settings

    maybe_seed_legacy_settings(db, user)
    session = create_session(db, user, request)

    popup = bool(flow.get("popup", True))
    opener_origin = flow.get("origin") or _request_origin(request)
    if popup:
        response = HTMLResponse(
            """
            <!DOCTYPE html>
            <html>
            <head><title>Login Complete</title></head>
            <body>
              <p>Login successful. You can close this window.</p>
              <script>
                if (window.opener) {
                  try {
                    window.opener.postMessage({ type: 'auth-complete' }, __TARGET_ORIGIN__);
                    window.opener.focus();
                  } catch (error) {
                    console.error('Failed to notify opener about auth completion', error);
                  }
                }
                setTimeout(() => window.close(), 150);
              </script>
            </body>
            </html>
            """
            .replace("__TARGET_ORIGIN__", json.dumps(opener_origin))
        )
    else:
        response = RedirectResponse(url="/")

    set_session_cookie(response, session.session_id)
    clear_temporary_flow_cookie(response, AUTH_FLOW_COOKIE)
    return response


@router.get("/me", response_model=AuthSessionResponse)
def get_current_auth_state(
    request: Request,
    user: User = Depends(get_current_user),
    session=Depends(get_current_session),
):
    """Return the current authenticated user and CSRF token."""
    return AuthSessionResponse(
        authenticated=True,
        csrf_token=session.csrf_token,
        user=AuthUserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            picture_url=user.picture_url,
        ),
    )


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    """Log out the current user."""
    from web.auth import destroy_session, get_session_from_request

    session = get_session_from_request(db, request)
    destroy_session(db, session)

    response = JSONResponse({"success": True})
    clear_session_cookie(response)
    return response
