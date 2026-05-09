"""Migration: add per-user ownership columns to business data tables."""

import sqlite3
from pathlib import Path


TABLES = (
    ("invoices", "idx_invoices_user_id"),
    ("transactions", "idx_transactions_user_id"),
    ("known_transactions", "idx_known_transactions_user_id"),
    ("vendor_aliases", "idx_vendor_aliases_user_id"),
    ("pdf_cache", "idx_pdf_cache_user_id"),
)


def migrate(db_path: Path) -> bool:
    """Add nullable user_id columns and indexes if they do not exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    applied = False

    for table_name, index_name in TABLES:
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [col[1] for col in cursor.fetchall()]

        if "user_id" not in columns:
            cursor.execute(
                f"ALTER TABLE {table_name} ADD COLUMN user_id INTEGER"
            )
            applied = True

        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
            (index_name,),
        )
        if cursor.fetchone() is None:
            cursor.execute(f"CREATE INDEX {index_name} ON {table_name}(user_id)")
            applied = True

    if applied:
        conn.commit()

    conn.close()
    return applied


if __name__ == "__main__":
    from web.config import DATA_DIR

    db_path = DATA_DIR / "invoice_matcher.db"
    if migrate(db_path):
        print("Migration applied: added user_id columns to business tables")
    else:
        print("Migration skipped: user_id columns already exist")
