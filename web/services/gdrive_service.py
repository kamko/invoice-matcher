"""Service for Google Drive integration."""

import io
import secrets
import hashlib
import base64
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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

    # Full drive scope for rename/modify operations on all files
    SCOPES = [
        "https://www.googleapis.com/auth/drive",
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
            state=state,
            prompt="consent",  # Force consent to get fresh scopes
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

    def find_subfolder(self, parent_id: str, folder_name: str) -> Optional[GDriveFolder]:
        """Find a subfolder by name within a parent folder.

        Args:
            parent_id: ID of the parent folder
            folder_name: Name of the subfolder to find (e.g., "202602")

        Returns:
            GDriveFolder if found, None otherwise
        """
        if not GDRIVE_AVAILABLE:
            raise RuntimeError("Google Drive libraries not installed")

        if not self._credentials:
            raise RuntimeError("Not authenticated with Google Drive")

        service = build("drive", "v3", credentials=self._credentials)

        query = f"'{parent_id}' in parents and name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"

        results = service.files().list(
            q=query,
            pageSize=1,
            fields="files(id, name, parents)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()

        files = results.get("files", [])
        if files:
            item = files[0]
            return GDriveFolder(
                id=item["id"],
                name=item["name"],
                parent_id=item.get("parents", [None])[0] if item.get("parents") else None,
            )
        return None

    def list_pdfs(self, folder_id: str) -> List[Dict[str, str]]:
        """List all PDF files in a folder without downloading.

        Returns:
            List of dicts with 'id' and 'name' keys.
        """
        if not GDRIVE_AVAILABLE:
            raise RuntimeError("Google Drive libraries not installed")

        if not self._credentials:
            raise RuntimeError("Not authenticated with Google Drive")

        service = build("drive", "v3", credentials=self._credentials)

        query = f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false"

        results = service.files().list(
            q=query,
            pageSize=100,
            fields="files(id, name)",
        ).execute()

        return results.get("files", [])

    def download_pdfs(self, folder_id: str, db=None, force_refresh: bool = False) -> Tuple[Path, List[str], Dict[str, str]]:
        """Download all PDFs from a folder, using cache when available.

        Args:
            folder_id: Google Drive folder ID
            db: Optional SQLAlchemy session for caching PDFs
            force_refresh: If True, re-fetch file list from GDrive (discovers new files).
                          Cached files with matching MD5 are still used (not re-downloaded).

        Returns:
            Tuple of (directory_path, list_of_filenames, dict_mapping_filename_to_file_id)
        """
        if not GDRIVE_AVAILABLE:
            raise RuntimeError("Google Drive libraries not installed")

        if not self._credentials:
            raise RuntimeError("Not authenticated with Google Drive")

        service = build("drive", "v3", credentials=self._credentials)

        # Create session-specific download directory
        session_dir = self._download_dir / folder_id
        session_dir.mkdir(exist_ok=True)

        # List PDF files in folder with MD5 checksums
        query = f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false"

        results = service.files().list(
            q=query,
            pageSize=100,
            fields="files(id, name, md5Checksum)",
        ).execute()

        downloaded_files = []
        file_id_map = {}  # filename -> gdrive file id
        cache_hits = 0
        cache_misses = 0

        # Import here to avoid circular imports
        if db:
            from web.database.models import PDFCache
            from datetime import datetime

        for item in results.get("files", []):
            file_id = item["id"]
            file_name = item["name"]
            md5_checksum = item.get("md5Checksum")
            file_path = session_dir / file_name

            content = None
            cache_reason = None

            # Check cache first - use cache if MD5 matches (even with force_refresh)
            # force_refresh only means "re-fetch file list", not "re-download unchanged files"
            if db:
                cached = db.query(PDFCache).filter(PDFCache.gdrive_file_id == file_id).first()
                if cached:
                    # Use cache if MD5 checksum matches (file unchanged)
                    if md5_checksum and cached.md5_checksum == md5_checksum:
                        # Cache hit - file unchanged, use cached content
                        content = cached.content
                        cached.last_accessed_at = datetime.utcnow()
                        cache_hits += 1
                    else:
                        cache_reason = f"MD5 mismatch: cached={cached.md5_checksum}, gdrive={md5_checksum}"
                else:
                    cache_reason = "not in cache"
            else:
                cache_reason = "no db session"

            if content is None:
                # Cache miss - download from Google Drive
                print(f"  [GDRIVE] Downloading {file_name}: {cache_reason}", flush=True)
                request = service.files().get_media(fileId=file_id)
                file_buffer = io.BytesIO()
                downloader = MediaIoBaseDownload(file_buffer, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()

                file_buffer.seek(0)
                content = file_buffer.read()
                cache_misses += 1

                # Store in cache
                if db:
                    from datetime import datetime
                    existing = db.query(PDFCache).filter(PDFCache.gdrive_file_id == file_id).first()
                    if existing:
                        existing.content = content
                        existing.filename = file_name
                        existing.file_size = len(content)
                        existing.md5_checksum = md5_checksum
                        existing.cached_at = datetime.utcnow()
                        existing.last_accessed_at = datetime.utcnow()
                    else:
                        cache_entry = PDFCache(
                            gdrive_file_id=file_id,
                            filename=file_name,
                            content=content,
                            file_size=len(content),
                            md5_checksum=md5_checksum,
                        )
                        db.add(cache_entry)

            # Write to disk for parsing
            with open(file_path, "wb") as f:
                f.write(content)

            downloaded_files.append(file_name)
            file_id_map[file_name] = file_id

        # Commit cache updates
        if db:
            db.commit()

        # Log cache efficiency
        total_files = len(downloaded_files)
        if total_files > 0:
            print(f"GDrive download: {total_files} files ({cache_hits} cached, {cache_misses} downloaded)", flush=True)

        return session_dir, downloaded_files, file_id_map

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

    def rename_file(self, file_id: str, new_name: str) -> bool:
        """Rename a file in Google Drive.

        Args:
            file_id: The ID of the file to rename
            new_name: The new filename

        Returns:
            True if successful
        """
        if not GDRIVE_AVAILABLE:
            raise RuntimeError("Google Drive libraries not installed")

        if not self._credentials:
            raise RuntimeError("Not authenticated with Google Drive")

        service = build("drive", "v3", credentials=self._credentials)

        service.files().update(
            fileId=file_id,
            body={"name": new_name},
        ).execute()

        return True

    def download_files_as_zip(self, file_ids_with_names: List[Tuple[str, str]], db=None) -> bytes:
        """Download multiple files from Google Drive and return as a zip.

        Uses cache when available to speed up downloads.

        Args:
            file_ids_with_names: List of (file_id, filename) tuples
            db: Optional SQLAlchemy session for cache access

        Returns:
            Zip file contents as bytes
        """
        import zipfile

        if not GDRIVE_AVAILABLE:
            raise RuntimeError("Google Drive libraries not installed")

        if not self._credentials:
            raise RuntimeError("Not authenticated with Google Drive")

        service = build("drive", "v3", credentials=self._credentials)

        # Import for cache access
        if db:
            from web.database.models import PDFCache
            from datetime import datetime

        # Create zip in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for file_id, filename in file_ids_with_names:
                try:
                    content = None

                    # Check cache first
                    if db:
                        cached = db.query(PDFCache).filter(PDFCache.gdrive_file_id == file_id).first()
                        if cached:
                            content = cached.content
                            cached.last_accessed_at = datetime.utcnow()

                    if content is None:
                        # Download file content from Google Drive
                        request = service.files().get_media(fileId=file_id)
                        file_buffer = io.BytesIO()
                        downloader = MediaIoBaseDownload(file_buffer, request)
                        done = False
                        while not done:
                            _, done = downloader.next_chunk()

                        file_buffer.seek(0)
                        content = file_buffer.read()

                        # Store in cache
                        if db:
                            existing = db.query(PDFCache).filter(PDFCache.gdrive_file_id == file_id).first()
                            if existing:
                                existing.content = content
                                existing.filename = filename
                                existing.file_size = len(content)
                                existing.cached_at = datetime.utcnow()
                                existing.last_accessed_at = datetime.utcnow()
                            else:
                                cache_entry = PDFCache(
                                    gdrive_file_id=file_id,
                                    filename=filename,
                                    content=content,
                                    file_size=len(content),
                                )
                                db.add(cache_entry)

                    # Add to zip
                    zip_file.writestr(filename, content)
                except Exception:
                    # Skip files that fail to download
                    continue

        # Commit cache updates
        if db:
            db.commit()

        zip_buffer.seek(0)
        return zip_buffer.read()
