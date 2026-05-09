"""Migration: Add document_type column to invoices table."""

import sqlite3
from pathlib import Path


def migrate(db_path: Path) -> bool:
    """Add document_type column to invoices table if it doesn't exist.

    Returns True if migration was applied, False if column already exists.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(invoices)")
    columns = [col[1] for col in cursor.fetchall()]

    if "document_type" in columns:
        conn.close()
        return False

    cursor.execute("""
        ALTER TABLE invoices
        ADD COLUMN document_type VARCHAR(20) DEFAULT 'invoice'
    """)

    # Conservative backfill for the most obvious legacy non-invoice filenames.
    cursor.execute("""
        UPDATE invoices
        SET document_type = CASE
            WHEN lower(filename) LIKE '%receipt%'
                OR lower(filename) LIKE '%blocek%'
                OR lower(filename) LIKE '%poklad%'
                OR lower(filename) LIKE '%ekasa%'
                OR lower(filename) LIKE '%paragon%'
            THEN 'receipt'
            WHEN lower(filename) LIKE '%zmluv%'
                OR lower(filename) LIKE '%contract%'
                OR lower(filename) LIKE '%vypis%'
                OR lower(filename) LIKE '%statement%'
            THEN 'other'
            ELSE document_type
        END
        WHERE lower(filename) LIKE '%receipt%'
            OR lower(filename) LIKE '%blocek%'
            OR lower(filename) LIKE '%poklad%'
            OR lower(filename) LIKE '%ekasa%'
            OR lower(filename) LIKE '%paragon%'
            OR lower(filename) LIKE '%zmluv%'
            OR lower(filename) LIKE '%contract%'
            OR lower(filename) LIKE '%vypis%'
            OR lower(filename) LIKE '%statement%'
    """)

    conn.commit()
    conn.close()
    return True


if __name__ == "__main__":
    from web.config import DATA_DIR

    db_path = DATA_DIR / "invoice_matcher.db"
    if migrate(db_path):
        print("Migration applied: added document_type column to invoices")
    else:
        print("Migration skipped: document_type column already exists")
