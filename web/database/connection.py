"""Database connection and session management."""

from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from web.config import settings, DATA_DIR


# Create engine
if settings.database_url.startswith("sqlite:///"):
    raw_path = settings.database_url.replace("sqlite:///", "", 1)
    DATABASE_PATH = Path(raw_path)
    if not DATABASE_PATH.is_absolute():
        DATABASE_PATH = (DATA_DIR.parent / raw_path).resolve()
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATABASE_URL = f"sqlite:///{DATABASE_PATH}"
else:
    DATABASE_PATH = DATA_DIR / "invoice_matcher.db"
    DATABASE_URL = settings.database_url

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Needed for SQLite
    echo=settings.debug,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """Dependency that provides a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Initialize the database by creating all tables and running migrations."""
    from .models import Base
    Base.metadata.create_all(bind=engine)

    if DATABASE_URL.startswith("sqlite:///"):
        with engine.begin() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")

    # Run migrations for existing databases
    from .migrations import run_all_migrations
    applied = run_all_migrations(DATABASE_PATH)
    if applied:
        print(f"Applied migrations: {', '.join(applied)}")
