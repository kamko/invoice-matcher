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
    """Initialize the database by creating all tables."""
    from .models import Base
    Base.metadata.create_all(bind=engine)
    # Run schema migrations for new columns
    _run_migrations()


def _run_migrations() -> None:
    """Run schema migrations for new columns on existing tables."""
    from sqlalchemy import text, inspect

    with engine.connect() as conn:
        inspector = inspect(engine)

        # Migration: Add is_manual_upload column to invoice_payments
        if 'invoice_payments' in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns('invoice_payments')]
            if 'is_manual_upload' not in columns:
                conn.execute(text(
                    "ALTER TABLE invoice_payments ADD COLUMN is_manual_upload BOOLEAN NOT NULL DEFAULT 0"
                ))
                conn.commit()
                print("[MIGRATION] Added is_manual_upload column to invoice_payments")
