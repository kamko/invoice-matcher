"""Tests for supporting-attachment schema migration."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from web.database.migrations.add_invoice_attachments import migrate


class InvoiceAttachmentMigrationTests(unittest.TestCase):
    def test_adds_attachment_columns_to_existing_invoice_table(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "legacy.db"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE invoices (id INTEGER PRIMARY KEY)")
            conn.commit()
            conn.close()

            self.assertTrue(migrate(db_path))

            conn = sqlite3.connect(db_path)
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(invoices)").fetchall()
            }
            indexes = {
                row[1] for row in conn.execute("PRAGMA index_list(invoices)").fetchall()
            }
            conn.close()

            self.assertIn("parent_invoice_id", columns)
            self.assertIn("attachment_index", columns)
            self.assertIn("uq_invoice_attachment_index", indexes)


if __name__ == "__main__":
    unittest.main()
