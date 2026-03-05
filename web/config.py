"""Configuration settings for the web application."""

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
    google_redirect_uri: str = "http://localhost:8000/api/gdrive/callback"

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8000"]

    # App
    debug: bool = False

    # LLM (OpenRouter)
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemini-2.5-flash-lite"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Allow extra env vars not defined in Settings


settings = Settings()

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
