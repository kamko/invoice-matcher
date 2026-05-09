"""Configuration settings for the web application."""

import json
import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "sqlite:///./data/invoice_matcher.db"

    # Google Drive OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_drive_redirect_uri: str = "http://localhost:8000/api/gdrive/callback"
    google_auth_redirect_uri: str = "http://localhost:8000/api/auth/callback"

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8000"]

    # App
    debug: bool = False
    secret_key: str = "dev-insecure-secret-key-change-me"
    trusted_hosts: list[str] = ["localhost", "127.0.0.1"]
    session_cookie_name: str = "invoice_matcher_session"
    session_cookie_secure: bool = False
    session_ttl_hours: int = 12
    temporary_flow_ttl_seconds: int = 600
    encryption_key: str = ""
    allowed_email_addresses: str = ""
    allowed_email_domains: str = ""

    # LLM (OpenRouter)
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemini-2.5-flash-lite"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Allow extra env vars not defined in Settings

    @property
    def allowed_emails(self) -> set[str]:
        return {
            item.strip().lower()
            for item in self.allowed_email_addresses.split(",")
            if item.strip()
        }

    @property
    def allowed_domains(self) -> set[str]:
        return {
            item.strip().lower()
            for item in self.allowed_email_domains.split(",")
            if item.strip()
        }


settings = Settings()

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
