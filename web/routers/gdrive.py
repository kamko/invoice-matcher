"""Router for Google Drive integration."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, File, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

from web.database import get_db

from web.schemas.gdrive import (
    GDriveAuthUrl,
    GDriveFolderList,
    GDriveDownloadRequest,
    GDriveDownloadResponse,
    GDriveUploadResponse,
)
from web.services.gdrive_service import GDriveService

router = APIRouter(prefix="/api/gdrive", tags=["gdrive"])

# Store credentials in memory (in production, use proper session management)
_gdrive_service = GDriveService()


@router.get("/status")
def get_gdrive_status():
    """Check if Google Drive integration is available and authenticated."""
    return {
        "available": _gdrive_service.is_available,
        "authenticated": _gdrive_service._credentials is not None,
    }


@router.post("/disconnect")
def disconnect_gdrive():
    """Disconnect from Google Drive (clear credentials)."""
    _gdrive_service.clear_credentials()
    return {"success": True, "message": "Disconnected from Google Drive"}


@router.get("/auth-url", response_model=GDriveAuthUrl)
def get_auth_url(state: Optional[str] = None):
    """Get the OAuth authorization URL for Google Drive."""
    if not _gdrive_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Google Drive integration not configured"
        )

    try:
        auth_url = _gdrive_service.get_auth_url(state)
        return GDriveAuthUrl(auth_url=auth_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/callback")
def handle_callback(code: str, state: Optional[str] = None):
    """Handle OAuth callback from Google."""
    if not _gdrive_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Google Drive integration not configured"
        )

    try:
        _gdrive_service.handle_callback(code)
        # Return HTML that closes popup and notifies parent window
        html_content = """
        <!DOCTYPE html>
        <html>
        <head><title>Google Drive Connected</title></head>
        <body>
            <p>Google Drive connected successfully! This window will close...</p>
            <script>
                if (window.opener) {
                    window.opener.postMessage({ type: 'gdrive-connected' }, '*');
                }
                window.close();
            </script>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content)
    except Exception as e:
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head><title>Error</title></head>
        <body>
            <p>Error connecting to Google Drive: {str(e)}</p>
            <button onclick="window.close()">Close</button>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content, status_code=400)


@router.get("/folders", response_model=GDriveFolderList)
def list_folders(
    parent_id: str = "root",
    all: bool = False,
    search: Optional[str] = None,
    shared: bool = False,
):
    """List folders in Google Drive.

    Args:
        parent_id: Parent folder ID (default "root")
        all: If True, list all folders (for search)
        search: Optional search term to filter by name
        shared: If True, list only folders shared with me
    """
    if not _gdrive_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Google Drive integration not configured"
        )

    if not _gdrive_service._credentials:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated with Google Drive"
        )

    try:
        if shared:
            folders = _gdrive_service.list_shared_folders()
        elif all or search:
            folders = _gdrive_service.list_all_folders(search=search)
        else:
            folders = _gdrive_service.list_folders(parent_id)
        return GDriveFolderList(folders=folders)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/folder/{folder_id}")
def get_folder_info(folder_id: str):
    """Get folder info by ID."""
    if not _gdrive_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Google Drive integration not configured"
        )

    if not _gdrive_service._credentials:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated with Google Drive"
        )

    try:
        folder = _gdrive_service.get_folder_info(folder_id)
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")
        return folder
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download", response_model=GDriveDownloadResponse)
def download_pdfs(request: GDriveDownloadRequest, db: Session = Depends(get_db)):
    """Download all PDFs from a Google Drive folder."""
    if not _gdrive_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Google Drive integration not configured"
        )

    if not _gdrive_service._credentials:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated with Google Drive"
        )

    try:
        download_path, files, _ = _gdrive_service.download_pdfs(request.folder_id, db)
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
):
    """Upload a PDF file to a Google Drive folder."""
    if not _gdrive_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Google Drive integration not configured"
        )

    if not _gdrive_service._credentials:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated with Google Drive"
        )

    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed"
        )

    try:
        content = await file.read()
        file_id = _gdrive_service.upload_pdf(folder_id, filename, content)
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
    db: Session = Depends(get_db),
):
    """Rename a file in Google Drive and update all references."""
    from web.database.models import PDFCache, Invoice

    if not _gdrive_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="Google Drive integration not configured"
        )

    if not _gdrive_service._credentials:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated with Google Drive"
        )

    if not new_filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail="Filename must end with .pdf"
        )

    try:
        # Rename in Google Drive
        _gdrive_service.rename_file(file_id, new_filename)

        old_filename = None

        # Update filename in PDFCache
        cached = db.query(PDFCache).filter(PDFCache.gdrive_file_id == file_id).first()
        if cached:
            old_filename = cached.filename
            cached.filename = new_filename

        # Update Invoice records
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
