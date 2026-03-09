"""Migration: Add currency column to invoices table."""

import sqlite3
from pathlib import Path


def migrate(db_path: Path) -> bool:
    """Add currency column to invoices table if it doesn't exist.

    Returns True if migration was applied, False if column already exists.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if column exists
    cursor.execute("PRAGMA table_info(invoices)")
    columns = [col[1] for col in cursor.fetchall()]

    if 'currency' in columns:
        conn.close()
        return False

    # Add the column with default value EUR
    cursor.execute("""
        ALTER TABLE invoices
        ADD COLUMN currency VARCHAR(3) DEFAULT 'EUR'
    """)

    conn.commit()
    conn.close()
    return True


if __name__ == "__main__":
    from web.config import DATA_DIR

    db_path = DATA_DIR / "invoice_matcher.db"
    if migrate(db_path):
        print(f"Migration applied: added currency column to invoices")
    else:
        print(f"Migration skipped: currency column already exists")
