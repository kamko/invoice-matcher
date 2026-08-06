"""Tests for manually supplied invoice upload metadata."""

import unittest
from io import BytesIO
from unittest.mock import Mock, patch

from fastapi import UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.database.models import Base, User
from web.routers.invoices import upload_invoice


class UploadInvoiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_persists_trimmed_accountant_comment(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        user = User(google_sub="upload-test", email="upload@example.com")
        db.add(user)
        db.commit()
        db.refresh(user)

        service = Mock()
        service.find_or_create_subfolder.return_value = "month-folder"
        service.upload_pdf.return_value = "drive-file"
        file = UploadFile(filename="invoice.pdf", file=BytesIO(b"%PDF-1.4 test"))

        with patch(
            "web.routers.invoices.get_gdrive_service_for_user",
            return_value=service,
        ):
            result = await upload_invoice(
                file=file,
                vendor="Vendor",
                invoice_date="2026-08-03",
                payment_type="wire",
                document_type="invoice",
                amount="249.0",
                currency="EUR",
                comment="  Poslat s augustovym exportom.  ",
                gdrive_folder_id="root-folder",
                skip_analyze=True,
                user=user,
                db=db,
            )

        self.assertEqual(result.comment, "Poslat s augustovym exportom.")
        db.close()
        engine.dispose()
