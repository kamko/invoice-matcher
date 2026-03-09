"""Migration: Add extracted_vendor column to transactions table."""

import sqlite3
from pathlib import Path


def migrate(db_path: Path) -> bool:
    """Add extracted_vendor column to transactions table if it doesn't exist.

    Returns True if migration was applied, False if column already exists.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if column exists
    cursor.execute("PRAGMA table_info(transactions)")
    columns = [col[1] for col in cursor.fetchall()]

    if 'extracted_vendor' in columns:
        conn.close()
        return False

    # Add the column
    cursor.execute("""
        ALTER TABLE transactions
        ADD COLUMN extracted_vendor VARCHAR(255)
    """)

    conn.commit()
    conn.close()
    return True


if __name__ == "__main__":
    from web.config import DATA_DIR

    db_path = DATA_DIR / "invoice_matcher.db"
    if migrate(db_path):
        print(f"Migration applied: added extracted_vendor column to transactions")
    else:
        print(f"Migration skipped: extracted_vendor column already exists")
