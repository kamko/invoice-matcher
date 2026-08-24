"""Migration: add vehicle, duplicate-detection, and export metadata to invoices."""

import hashlib
import sqlite3
from pathlib import Path


def migrate(db_path: Path) -> bool:
    """Add upload metadata and backfill hashes for cached PDFs."""
    conn = sqlite3.connect(db_path)
    changed = False
    try:
        columns = {
            column[1]
            for column in conn.execute("PRAGMA table_info(invoices)").fetchall()
        }
        additions = {
            "vehicle_registration": "TEXT",
            "is_vehicle_expense": "BOOLEAN NOT NULL DEFAULT 0",
            "content_sha256": "TEXT",
            "include_in_export": "BOOLEAN NOT NULL DEFAULT 1",
        }
        for name, definition in additions.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE invoices ADD COLUMN {name} {definition}")
                changed = True

        cache_columns = {
            column[1]
            for column in conn.execute("PRAGMA table_info(pdf_cache)").fetchall()
        }
        if "content" in cache_columns:
            rows = conn.execute(
                """
                SELECT invoices.id, pdf_cache.content
                FROM invoices
                JOIN pdf_cache ON pdf_cache.gdrive_file_id = invoices.gdrive_file_id
                WHERE invoices.content_sha256 IS NULL
                """
            ).fetchall()
            for invoice_id, content in rows:
                if content is not None:
                    conn.execute(
                        "UPDATE invoices SET content_sha256 = ? WHERE id = ?",
                        (hashlib.sha256(content).hexdigest(), invoice_id),
                    )
                    changed = True

        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_invoices_user_content_sha256 "
            "ON invoices (user_id, content_sha256)"
        )
        conn.commit()
        return changed
    finally:
        conn.close()
