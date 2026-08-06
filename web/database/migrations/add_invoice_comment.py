"""Migration: add an optional accountant comment to invoices."""

import sqlite3
from pathlib import Path


def migrate(db_path: Path) -> bool:
    """Add the comment column when upgrading an existing SQLite database."""
    conn = sqlite3.connect(db_path)
    try:
        columns = {
            column[1]
            for column in conn.execute("PRAGMA table_info(invoices)").fetchall()
        }
        if "comment" in columns:
            return False

        conn.execute("ALTER TABLE invoices ADD COLUMN comment TEXT")
        conn.commit()
        return True
    finally:
        conn.close()


if __name__ == "__main__":
    from web.config import DATA_DIR

    if migrate(DATA_DIR / "invoice_matcher.db"):
        print("Migration applied: added invoice comment column")
    else:
        print("Migration skipped: invoice comment column already exists")
