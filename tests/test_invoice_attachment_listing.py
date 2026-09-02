"""Tests for grouped invoice and attachment list counts."""

import unittest
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.database.models import Base, Invoice, User
from web.routers.invoices import list_invoices


class InvoiceAttachmentListingTests(unittest.TestCase):
    def test_total_excludes_attachments_and_reports_them_separately(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        user = User(google_sub="list-owner", email="list@example.com")
        db.add(user)
        db.commit()
        db.refresh(user)

        primary = Invoice(
            user_id=user.id,
            filename="2026-08-31-001_wire_orlen.pdf",
            invoice_date=date(2026, 8, 31),
            amount="199.16",
            status="unmatched",
        )
        db.add(primary)
        db.flush()
        db.add_all([
            Invoice(
                user_id=user.id,
                filename="2026-08-31-001_wire_orlen_att_01.pdf",
                invoice_date=primary.invoice_date,
                parent_invoice_id=primary.id,
                attachment_index=1,
                include_in_export=False,
                status="reference",
            ),
            Invoice(
                user_id=user.id,
                filename="2026-08-31-001_wire_orlen_att_02.pdf",
                invoice_date=primary.invoice_date,
                parent_invoice_id=primary.id,
                attachment_index=2,
                include_in_export=False,
                status="reference",
            ),
        ])
        db.commit()

        result = list_invoices(None, None, None, user, db)

        self.assertEqual(result.total, 1)
        self.assertEqual(result.attachments, 2)
        self.assertEqual(len(result.invoices), 3)

        filtered_result = list_invoices(None, "unmatched", "invoice", user, db)
        self.assertEqual(filtered_result.total, 1)
        self.assertEqual(filtered_result.attachments, 2)
        self.assertEqual(len(filtered_result.invoices), 3)
        db.close()
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
