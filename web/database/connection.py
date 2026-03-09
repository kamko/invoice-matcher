"""Database connection and session management."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from web.config import settings, DATA_DIR


# Create engine
DATABASE_PATH = DATA_DIR / "invoice_matcher.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Needed for SQLite
    echo=settings.debug,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


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

    # Run migrations for existing databases
    from .migrations import run_all_migrations
    applied = run_all_migrations(DATABASE_PATH)
    if applied:
        print(f"Applied migrations: {', '.join(applied)}")
