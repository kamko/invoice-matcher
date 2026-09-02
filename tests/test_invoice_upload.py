"""Tests for manually supplied invoice upload metadata."""

import unittest
from datetime import date
from io import BytesIO
from unittest.mock import Mock, patch

from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.database.models import Base, Invoice, User, Vehicle
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
                vehicle_id=None,
                vehicle_registration=None,
                is_vehicle_expense=False,
                include_in_export=True,
                parent_invoice_id=None,
                attachment_index=None,
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
        vehicle = Vehicle(
            user_id=user.id,
            name="Toyota Corolla",
            registration="KE885HH",
        )
        db.add(vehicle)
        db.commit()
        db.refresh(vehicle)

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
                vehicle_id=vehicle.id,
                vehicle_registration="BA123CD",
                is_vehicle_expense=True,
                include_in_export=True,
                parent_invoice_id=None,
                attachment_index=None,
                gdrive_folder_id="root-folder",
                skip_analyze=True,
                user=user,
                db=db,
            )

        self.assertEqual(result.vehicle_registration, "KE885HH")
        self.assertEqual(result.vehicle_id, vehicle.id)
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
                vehicle_id=None,
                vehicle_registration="KE885HH",
                is_vehicle_expense=True,
                include_in_export=False,
                parent_invoice_id=None,
                attachment_index=None,
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
                    vehicle_id=None,
                    vehicle_registration=None,
                    is_vehicle_expense=False,
                    include_in_export=True,
                    parent_invoice_id=None,
                    attachment_index=None,
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

    async def test_attachment_uses_primary_filename_without_payment_or_amount(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine)()
        user = User(google_sub="attachment-test", email="attachment@example.com")
        db.add(user)
        db.commit()
        db.refresh(user)
        primary = Invoice(
            user_id=user.id,
            filename="2026-08-31-001_wire_orlen-unipetrol-slovakia-sro.pdf",
            vendor="ORLEN Unipetrol Slovakia, s.r.o.",
            invoice_date=date(2026, 8, 31),
            payment_type="wire",
            amount="199.16",
            include_in_export=True,
            status="unmatched",
        )
        db.add(primary)
        db.commit()
        db.refresh(primary)

        service = Mock()
        service.find_or_create_subfolder.return_value = "month-folder"
        service.upload_pdf.return_value = "attachment-file"
        file = UploadFile(filename="detail.pdf", file=BytesIO(b"%PDF attachment"))

        with patch("web.routers.invoices.get_gdrive_service_for_user", return_value=service):
            result = await upload_invoice(
                file=file,
                vendor="Wrong standalone vendor",
                invoice_date=None,
                payment_type="card",
                document_type="invoice",
                amount="999.00",
                currency="EUR",
                comment=None,
                vehicle_id=None,
                vehicle_registration=None,
                is_vehicle_expense=False,
                include_in_export=True,
                parent_invoice_id=primary.id,
                attachment_index=1,
                gdrive_folder_id="root-folder",
                skip_analyze=True,
                user=user,
                db=db,
            )

        expected_name = "2026-08-31-001_wire_orlen-unipetrol-slovakia-sro_att_01.pdf"
        self.assertEqual(result.filename, expected_name)
        self.assertEqual(result.parent_invoice_id, primary.id)
        self.assertEqual(result.attachment_index, 1)
        self.assertIsNone(result.amount)
        self.assertIsNone(result.payment_type)
        self.assertFalse(result.include_in_export)
        self.assertEqual(result.status, "reference")
        self.assertEqual(service.upload_pdf.call_args.args[1], expected_name)
        db.close()
        engine.dispose()
