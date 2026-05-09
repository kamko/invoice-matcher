"""Router for Google Drive integration."""

import base64
import hashlib
import json
import secrets
import urllib.parse
import urllib.request
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from google.oauth2.credentials import Credentials
from sqlalchemy.orm import Session

from web.auth import (
    GDRIVE_FLOW_COOKIE,
    GDRIVE_FLOW_SALT,
    clear_temporary_flow_cookie,
    get_current_user,
    load_temporary_flow_cookie,
    set_temporary_flow_cookie,
)
from web.config import settings
from web.database import get_db
from web.database.models import GoogleDriveConnection, PDFCache, Invoice, User
from web.schemas.gdrive import (
    GDriveAuthUrl,
    GDriveFolderList,
    GDriveDownloadRequest,
    GDriveDownloadResponse,
    GDriveUploadResponse,
)
from web.security import decrypt_json, encrypt_json
from web.services.gdrive_service import GDriveService

router = APIRouter(prefix="/api/gdrive", tags=["gdrive"])
_gdrive_service = GDriveService()


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def _build_google_drive_auth_url(state: str, verifier: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_drive_redirect_uri,
        "response_type": "code",
        "scope": " ".join(GDriveService.SCOPES),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
        "code_challenge": _code_challenge(verifier),
        "code_challenge_method": "S256",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def _exchange_drive_code(code: str, code_verifier: str) -> dict:
    payload = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_drive_redirect_uri,
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
        raise HTTPException(status_code=400, detail=f"Google Drive token exchange failed: {exc}") from exc


def get_gdrive_credentials_for_user(db: Session, user: User) -> Optional[Credentials]:
    """Load stored Google Drive credentials for the user."""
    connection = db.query(GoogleDriveConnection).filter(
        GoogleDriveConnection.user_id == user.id
    ).first()
    if not connection:
        return None

    data = decrypt_json(connection.encrypted_credentials)
    return Credentials.from_authorized_user_info(data, scopes=GDriveService.SCOPES)


def get_gdrive_service_for_user(db: Session, user: User) -> GDriveService:
    """Return a user-scoped Google Drive service."""
    credentials = get_gdrive_credentials_for_user(db, user)
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated with Google Drive")
    return GDriveService(credentials)


@router.get("/status")
def get_gdrive_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check if Google Drive integration is available and authenticated."""
    connection = db.query(GoogleDriveConnection).filter(
        GoogleDriveConnection.user_id == user.id
    ).first()
    return {
        "available": _gdrive_service.is_available,
        "authenticated": connection is not None,
    }


@router.post("/disconnect")
def disconnect_gdrive(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Disconnect from Google Drive for the current user."""
    connection = db.query(GoogleDriveConnection).filter(
        GoogleDriveConnection.user_id == user.id
    ).first()
    if connection:
        db.delete(connection)
        db.commit()
    return {"success": True, "message": "Disconnected from Google Drive"}


@router.get("/auth-url", response_model=GDriveAuthUrl)
def get_auth_url(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Get the OAuth authorization URL for Google Drive."""
    if not _gdrive_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Google Drive integration not configured"
        )

    verifier = secrets.token_urlsafe(48)
    state = secrets.token_urlsafe(24)
    response = JSONResponse({"auth_url": _build_google_drive_auth_url(state, verifier)})
    set_temporary_flow_cookie(
        response,
        GDRIVE_FLOW_COOKIE,
        GDRIVE_FLOW_SALT,
        {
            "state": state,
            "code_verifier": verifier,
            "user_id": user.id,
            "origin": request.headers.get("origin") or request.base_url.scheme + "://" + request.base_url.netloc,
        },
    )
    return response


@router.get("/callback")
def handle_callback(
    request: Request,
    code: str,
    state: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Handle OAuth callback from Google."""
    if not _gdrive_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Google Drive integration not configured"
        )

    flow = load_temporary_flow_cookie(request, GDRIVE_FLOW_COOKIE, GDRIVE_FLOW_SALT)
    if flow.get("user_id") != user.id:
        raise HTTPException(status_code=400, detail="Google Drive auth flow does not belong to this user")
    if state != flow.get("state"):
        raise HTTPException(status_code=400, detail="State mismatch during Google Drive authentication")

    tokens = _exchange_drive_code(code, flow["code_verifier"])
    creds_payload = {
        "token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "scopes": GDriveService.SCOPES,
    }

    connection = db.query(GoogleDriveConnection).filter(
        GoogleDriveConnection.user_id == user.id
    ).first()

    if not connection:
        connection = GoogleDriveConnection(
            user_id=user.id,
            email=user.email,
            encrypted_credentials=encrypt_json(creds_payload),
            scopes=" ".join(GDriveService.SCOPES),
        )
        db.add(connection)
    else:
        if not creds_payload["refresh_token"]:
            existing_payload = decrypt_json(connection.encrypted_credentials)
            creds_payload["refresh_token"] = existing_payload.get("refresh_token")
        connection.email = user.email
        connection.encrypted_credentials = encrypt_json(creds_payload)
        connection.scopes = " ".join(GDriveService.SCOPES)

    db.commit()
    opener_origin = flow.get("origin", request.base_url.scheme + "://" + request.base_url.netloc)

    response = HTMLResponse(
        """
        <!DOCTYPE html>
        <html>
        <head><title>Google Drive Connected</title></head>
        <body>
            <p>Google Drive connected successfully! This window will close...</p>
            <script>
                if (window.opener) {
                    window.opener.postMessage({ type: 'gdrive-connected' }, __TARGET_ORIGIN__);
                }
                window.close();
            </script>
        </body>
        </html>
        """
        .replace("__TARGET_ORIGIN__", json.dumps(opener_origin))
    )
    clear_temporary_flow_cookie(response, GDRIVE_FLOW_COOKIE)
    return response


@router.get("/folders", response_model=GDriveFolderList)
def list_folders(
    parent_id: str = "root",
    all: bool = False,
    search: Optional[str] = None,
    shared: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List folders in Google Drive."""
    if not _gdrive_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Google Drive integration not configured"
        )

    service = get_gdrive_service_for_user(db, user)

    try:
        if shared:
            folders = service.list_shared_folders()
        elif all or search:
            folders = service.list_all_folders(search=search)
        else:
            folders = service.list_folders(parent_id)
        return GDriveFolderList(folders=folders)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/folder/{folder_id}")
def get_folder_info(
    folder_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get folder info by ID."""
    if not _gdrive_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Google Drive integration not configured"
        )

    service = get_gdrive_service_for_user(db, user)

    try:
        folder = service.get_folder_info(folder_id)
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")
        return folder
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download", response_model=GDriveDownloadResponse)
def download_pdfs(
    request: GDriveDownloadRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download all PDFs from a Google Drive folder."""
    if not _gdrive_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Google Drive integration not configured"
        )

    service = get_gdrive_service_for_user(db, user)

    try:
        download_path, files, _ = service.download_pdfs(request.folder_id, db)
        return GDriveDownloadResponse(
            success=True,
            download_path=str(download_path),
            file_count=len(files),
            files=files,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload", response_model=GDriveUploadResponse)
async def upload_pdf(
    folder_id: str = Form(...),
    filename: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a PDF file to a Google Drive folder."""
    if not _gdrive_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Google Drive integration not configured"
        )

    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed"
        )

    service = get_gdrive_service_for_user(db, user)

    try:
        content = await file.read()
        file_id = service.upload_pdf(folder_id, filename, content)
        return GDriveUploadResponse(
            success=True,
            file_id=file_id,
            filename=filename,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rename")
def rename_file(
    file_id: str = Form(...),
    new_filename: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rename a file in Google Drive and update all references."""
    if not _gdrive_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Google Drive integration not configured"
        )

    if not new_filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail="Filename must end with .pdf"
        )

    service = get_gdrive_service_for_user(db, user)

    try:
        service.rename_file(file_id, new_filename)

        old_filename = None

        cached = db.query(PDFCache).filter(PDFCache.gdrive_file_id == file_id).first()
        if cached:
            old_filename = cached.filename
            cached.filename = new_filename

        invoices = db.query(Invoice).filter(
            Invoice.gdrive_file_id == file_id
        ).all()
        for invoice in invoices:
            invoice.filename = new_filename

        db.commit()

        return {
            "success": True,
            "file_id": file_id,
            "old_filename": old_filename,
            "new_filename": new_filename,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
