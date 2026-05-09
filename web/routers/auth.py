"""Authentication router for Google login and app sessions."""

import hashlib
import base64
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
from web.database.models import User
from web.schemas.auth import AuthSessionResponse, AuthUserResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def _build_google_auth_url(state: str, nonce: str, code_challenge: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_auth_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "include_granted_scopes": "true",
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
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
            "origin": request.headers.get("origin") or request.base_url.scheme + "://" + request.base_url.netloc,
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

    from web.auth import maybe_seed_legacy_settings

    maybe_seed_legacy_settings(db, user)
    session = create_session(db, user, request)

    popup = bool(flow.get("popup", True))
    opener_origin = flow.get("origin", request.base_url.scheme + "://" + request.base_url.netloc)
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
                  window.opener.postMessage({ type: 'auth-complete' }, __TARGET_ORIGIN__);
                }
                window.close();
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
