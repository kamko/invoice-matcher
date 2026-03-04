"""Service for Google Drive integration."""

import io
import secrets
import hashlib
import base64
from pathlib import Path
from typing import List, Optional, Tuple

from web.config import settings, DATA_DIR
from web.schemas.gdrive import GDriveFolder

# Google Drive imports (will be available after installing dependencies)
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
    GDRIVE_AVAILABLE = True
except ImportError:
    GDRIVE_AVAILABLE = False


class GDriveService:
    """Service for Google Drive operations."""

    # Need both scopes: file for upload, readonly for listing folders outside our app
    SCOPES = [
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive.readonly",
    ]

    def __init__(self):
        self._credentials: Optional[Credentials] = None
        self._download_dir = DATA_DIR / "downloads"
        self._download_dir.mkdir(exist_ok=True)
        # Store the flow to preserve code_verifier for PKCE
        self._pending_flow: Optional[Flow] = None

    @property
    def is_available(self) -> bool:
        """Check if Google Drive integration is available."""
        return GDRIVE_AVAILABLE and bool(settings.google_client_id)

    def _create_flow(self) -> Flow:
        """Create a new OAuth flow."""
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uris": [settings.google_redirect_uri],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=self.SCOPES,
        )
        flow.redirect_uri = settings.google_redirect_uri
        return flow

    def get_auth_url(self, state: Optional[str] = None) -> str:
        """Get the OAuth authorization URL."""
        if not GDRIVE_AVAILABLE:
            raise RuntimeError("Google Drive libraries not installed")

        # Create and store the flow for later use in callback
        self._pending_flow = self._create_flow()

        auth_url, _ = self._pending_flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            state=state,
            prompt="consent",  # Force consent to get refresh token
        )

        return auth_url

    def handle_callback(self, code: str) -> Credentials:
        """Handle OAuth callback and get credentials."""
        if not GDRIVE_AVAILABLE:
            raise RuntimeError("Google Drive libraries not installed")

        # Use the stored flow that has the code_verifier
        if self._pending_flow is None:
            # Fallback: create new flow (may fail with PKCE error)
            self._pending_flow = self._create_flow()

        try:
            self._pending_flow.fetch_token(code=code)
            self._credentials = self._pending_flow.credentials
        except Exception as e:
            # If scope mismatch, clear and retry
            if "Scope has changed" in str(e):
                self._credentials = None
                self._pending_flow = None
                raise RuntimeError("Please re-authenticate with Google Drive (scopes changed)")
            raise

        # Clear the pending flow
        self._pending_flow = None

        return self._credentials

    def clear_credentials(self) -> None:
        """Clear stored credentials (for re-authentication)."""
        self._credentials = None
        self._pending_flow = None

    def set_credentials(self, credentials: Credentials) -> None:
        """Set credentials for API calls."""
        self._credentials = credentials

    def list_folders(self, parent_id: str = "root") -> List[GDriveFolder]:
        """List folders in Google Drive."""
        if not GDRIVE_AVAILABLE:
            raise RuntimeError("Google Drive libraries not installed")

        if not self._credentials:
            raise RuntimeError("Not authenticated with Google Drive")

        service = build("drive", "v3", credentials=self._credentials)

        # Query for folders in the specified parent
        if parent_id == "root":
            query = "'root' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        else:
            query = f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"

        results = service.files().list(
            q=query,
            pageSize=100,
            fields="files(id, name, parents)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()

        folders = []
        for item in results.get("files", []):
            folders.append(GDriveFolder(
                id=item["id"],
                name=item["name"],
                parent_id=item.get("parents", [None])[0] if item.get("parents") else None,
            ))

        # Sort by name
        folders.sort(key=lambda f: f.name.lower())

        return folders

    def list_all_folders(self) -> List[GDriveFolder]:
        """List ALL folders in Google Drive (for search/debug)."""
        if not GDRIVE_AVAILABLE:
            raise RuntimeError("Google Drive libraries not installed")

        if not self._credentials:
            raise RuntimeError("Not authenticated with Google Drive")

        service = build("drive", "v3", credentials=self._credentials)

        # Get all folders
        query = "mimeType='application/vnd.google-apps.folder' and trashed=false"

        results = service.files().list(
            q=query,
            pageSize=100,
            fields="files(id, name, parents)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()

        folders = []
        for item in results.get("files", []):
            folders.append(GDriveFolder(
                id=item["id"],
                name=item["name"],
                parent_id=item.get("parents", [None])[0] if item.get("parents") else None,
            ))

        folders.sort(key=lambda f: f.name.lower())
        return folders

    def download_pdfs(self, folder_id: str) -> Tuple[Path, List[str]]:
        """Download all PDFs from a folder."""
        if not GDRIVE_AVAILABLE:
            raise RuntimeError("Google Drive libraries not installed")

        if not self._credentials:
            raise RuntimeError("Not authenticated with Google Drive")

        service = build("drive", "v3", credentials=self._credentials)

        # Create session-specific download directory
        session_dir = self._download_dir / folder_id
        session_dir.mkdir(exist_ok=True)

        # List PDF files in folder
        query = f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false"

        results = service.files().list(
            q=query,
            pageSize=100,
            fields="files(id, name)",
        ).execute()

        downloaded_files = []

        for item in results.get("files", []):
            file_id = item["id"]
            file_name = item["name"]
            file_path = session_dir / file_name

            # Download file
            request = service.files().get_media(fileId=file_id)

            with open(file_path, "wb") as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()

            downloaded_files.append(file_name)

        return session_dir, downloaded_files

    def list_files_in_folder(self, folder_id: str) -> List[str]:
        """List all file names in a folder."""
        if not GDRIVE_AVAILABLE:
            raise RuntimeError("Google Drive libraries not installed")

        if not self._credentials:
            raise RuntimeError("Not authenticated with Google Drive")

        service = build("drive", "v3", credentials=self._credentials)

        query = f"'{folder_id}' in parents and trashed=false"

        results = service.files().list(
            q=query,
            pageSize=500,
            fields="files(name)",
        ).execute()

        return [item["name"] for item in results.get("files", [])]

    def upload_pdf(self, folder_id: str, filename: str, content: bytes) -> str:
        """Upload a PDF file to a Google Drive folder.

        Args:
            folder_id: The ID of the folder to upload to
            filename: The name for the uploaded file
            content: The file content as bytes

        Returns:
            The ID of the uploaded file
        """
        if not GDRIVE_AVAILABLE:
            raise RuntimeError("Google Drive libraries not installed")

        if not self._credentials:
            raise RuntimeError("Not authenticated with Google Drive")

        service = build("drive", "v3", credentials=self._credentials)

        file_metadata = {
            "name": filename,
            "parents": [folder_id],
            "mimeType": "application/pdf",
        }

        media = MediaIoBaseUpload(
            io.BytesIO(content),
            mimetype="application/pdf",
            resumable=True,
        )

        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id",
        ).execute()

        return file.get("id")
