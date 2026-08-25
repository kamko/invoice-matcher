"""Tests for manually supplied invoice upload metadata."""

import unittest
from io import BytesIO
from unittest.mock import Mock, patch

from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.database.models import Base, Invoice, User
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
                vehicle_registration=None,
                is_vehicle_expense=False,
                include_in_export=True,
                gdrive_folder_id="root-folder",
                skip_analyze=True,
                user=user,
                db=db,
            )

        self.assertEqual(result.comment, "Poslat s augustovym exportom.")
        db.close()
        engine.dispose()

    async def test_vehicle_registration_is_normalized_and_added_to_filename(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        user = User(google_sub="vehicle-test", email="vehicle@example.com")
        db.add(user)
        db.commit()
        db.refresh(user)

        service = Mock()
        service.find_or_create_subfolder.return_value = "month-folder"
        service.upload_pdf.return_value = "vehicle-file"
        file = UploadFile(filename="fuel.pdf", file=BytesIO(b"%PDF vehicle"))

        with patch("web.routers.invoices.get_gdrive_service_for_user", return_value=service):
            result = await upload_invoice(
                file=file,
                vendor="OMV",
                invoice_date="2026-08-03",
                payment_type="card",
                document_type="receipt",
                amount="75.0",
                currency="EUR",
                comment=None,
                vehicle_registration="ke-885-hh",
                is_vehicle_expense=True,
                include_in_export=True,
                gdrive_folder_id="root-folder",
                skip_analyze=True,
                user=user,
                db=db,
            )

        self.assertEqual(result.vehicle_registration, "KE885HH")
        self.assertTrue(result.is_vehicle_expense)
        self.assertTrue(result.filename.endswith("_KE885HH.pdf"))
        service.upload_pdf.assert_called_once()
        self.assertTrue(service.upload_pdf.call_args.args[1].endswith("_KE885HH.pdf"))
        db.close()
        engine.dispose()

    async def test_internal_file_is_saved_as_reference(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        user = User(google_sub="reference-test", email="reference@example.com")
        db.add(user)
        db.commit()
        db.refresh(user)

        service = Mock()
        service.find_or_create_subfolder.return_value = "month-folder"
        service.upload_pdf.return_value = "reference-file"
        file = UploadFile(filename="statement.pdf", file=BytesIO(b"%PDF statement"))

        with patch("web.routers.invoices.get_gdrive_service_for_user", return_value=service):
            result = await upload_invoice(
                file=file,
                vendor="OMV",
                invoice_date="2026-08-03",
                payment_type="card",
                document_type="other",
                amount=None,
                currency="EUR",
                comment=None,
                vehicle_registration="KE885HH",
                is_vehicle_expense=True,
                include_in_export=False,
                gdrive_folder_id="root-folder",
                skip_analyze=True,
                user=user,
                db=db,
            )

        self.assertFalse(result.include_in_export)
        self.assertEqual(result.status, "reference")
        db.close()
        engine.dispose()

    async def test_duplicate_pdf_is_rejected_before_drive_upload(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        user = User(google_sub="duplicate-test", email="duplicate@example.com")
        db.add(user)
        db.commit()
        db.refresh(user)

        duplicate_content = b"%PDF duplicate"
        import hashlib
        db.add(Invoice(
            user_id=user.id,
            filename="existing.pdf",
            content_sha256=hashlib.sha256(duplicate_content).hexdigest(),
        ))
        db.commit()

        service = Mock()
        file = UploadFile(filename="again.pdf", file=BytesIO(duplicate_content))
        with patch("web.routers.invoices.get_gdrive_service_for_user", return_value=service):
            with self.assertRaises(HTTPException) as raised:
                await upload_invoice(
                    file=file,
                    vendor="Vendor",
                    invoice_date="2026-08-03",
                    payment_type="wire",
                    document_type="invoice",
                    amount="249.0",
                    currency="EUR",
                    comment=None,
                    vehicle_registration=None,
                    is_vehicle_expense=False,
                    include_in_export=True,
                    gdrive_folder_id="root-folder",
                    skip_analyze=True,
                    user=user,
                    db=db,
                )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("existing.pdf", raised.exception.detail)
        service.find_or_create_subfolder.assert_not_called()
        service.upload_pdf.assert_not_called()
        db.close()
        engine.dispose()
