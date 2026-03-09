"""Schemas for Google Drive endpoints."""

from typing import List, Optional
from pydantic import BaseModel


class GDriveAuthUrl(BaseModel):
    """Response with OAuth URL."""

    auth_url: str


class GDriveFolder(BaseModel):
    """A Google Drive folder."""

    id: str
    name: str
    parent_id: Optional[str] = None
    shared: bool = False


class GDriveFolderList(BaseModel):
    """List of Google Drive folders."""

    folders: List[GDriveFolder]


class GDriveDownloadRequest(BaseModel):
    """Request to download PDFs from a folder."""

    folder_id: str


class GDriveDownloadResponse(BaseModel):
    """Response after downloading PDFs."""

    success: bool
    download_path: str
    file_count: int
    files: List[str]


class GDriveUploadResponse(BaseModel):
    """Response after uploading a PDF."""

    success: bool
    file_id: str
    filename: str
