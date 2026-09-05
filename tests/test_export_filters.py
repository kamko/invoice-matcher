"""Tests for accountant export eligibility."""

import unittest
from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.database.models import Base, Invoice, User, Transaction
from web.routers.dashboard import _get_exportable_invoices


class ExportEligibilityTests(unittest.TestCase):
    def test_internal_references_are_never_exported(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        user = User(google_sub="export-test", email="export@example.com")
        db.add(user)
        db.commit()
        db.refresh(user)

        db.add(Transaction(id="paired-payment", user_id=user.id, date=date(2026, 8, 3), amount=-10, type="expense", status="matched"))
        db.add_all([
            Invoice(
                user_id=user.id,
                gdrive_file_id="exportable",
                filename="exportable.pdf",
                transaction_id="paired-payment",
                invoice_date=date(2026, 8, 3),
                status="matched",
                include_in_export=True,
            ),
            Invoice(
                user_id=user.id,
                gdrive_file_id="internal",
                filename="internal.pdf",
                invoice_date=date(2026, 8, 3),
                status="matched",
                include_in_export=False,
            ),
            Invoice(
                user_id=user.id,
                gdrive_file_id="cash",
                filename="cash.pdf",
                invoice_date=date(2026, 8, 4),
                status="cash",
                include_in_export=True,
            ),
            Invoice(
                user_id=user.id,
                gdrive_file_id="unmatched",
                filename="unmatched.pdf",
                invoice_date=date(2026, 8, 5),
                status="unmatched",
                include_in_export=True,
            ),
        ])
        db.commit()

        filenames = {
            invoice.filename
            for invoice in _get_exportable_invoices(db, user.id, 2026, 8)
        }

        self.assertEqual(filenames, {"exportable.pdf"})
        db.close()
        engine.dispose()
