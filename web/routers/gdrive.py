"""Router for Google Drive integration."""

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from google.oauth2.credentials import Credentials
from sqlalchemy.orm import Session

from web.auth import get_current_user
from web.database import get_db
from web.database.models import GoogleDriveConnection, PDFCache, Invoice, User
from web.schemas.gdrive import (
    GDriveFolderList,
    GDriveDownloadRequest,
    GDriveDownloadResponse,
    GDriveUploadResponse,
)
from web.security import decrypt_json
from web.services.gdrive_service import GDriveService

router = APIRouter(prefix="/api/gdrive", tags=["gdrive"])
_gdrive_service = GDriveService()


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
        download_path, files, _ = service.download_pdfs(request.folder_id, db, user_id=user.id)
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

        cached = db.query(PDFCache).filter(
            PDFCache.gdrive_file_id == file_id,
            PDFCache.user_id == user.id,
        ).first()
        if cached:
            old_filename = cached.filename
            cached.filename = new_filename

        invoices = db.query(Invoice).filter(
            Invoice.gdrive_file_id == file_id,
            Invoice.user_id == user.id,
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
