"""Migration: link supporting PDFs to their primary invoice."""

import sqlite3
from pathlib import Path


def migrate(db_path: Path) -> bool:
    """Add optional parent invoice and attachment position columns."""
    conn = sqlite3.connect(db_path)
    changed = False
    try:
        columns = {
            column[1]
            for column in conn.execute("PRAGMA table_info(invoices)").fetchall()
        }
        if "parent_invoice_id" not in columns:
            conn.execute(
                "ALTER TABLE invoices ADD COLUMN parent_invoice_id INTEGER REFERENCES invoices(id)"
            )
            changed = True
        if "attachment_index" not in columns:
            conn.execute("ALTER TABLE invoices ADD COLUMN attachment_index INTEGER")
            changed = True

        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_invoices_parent_invoice_id ON invoices (parent_invoice_id)"
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_invoice_attachment_index
            ON invoices (parent_invoice_id, attachment_index)
            """
        )
        conn.commit()
        return changed
    finally:
        conn.close()
