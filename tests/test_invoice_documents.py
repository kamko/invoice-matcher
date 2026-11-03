import unittest
from datetime import date
from io import BytesIO
from unittest.mock import Mock, patch

import fitz
from fastapi import HTTPException, UploadFile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from web.database.models import Base, Invoice, Transaction, PDFCache, User
from web.routers.invoices import replace_invoice_pdf, delete_invoice


class InvoiceDocumentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.user = User(google_sub='test', email='test@example.com')
        self.db.add(self.user)
        self.db.flush()
        self.transaction = Transaction(id='tx', user_id=self.user.id, date=date.today(), amount=-10, status='matched')
        self.invoice = Invoice(user_id=self.user.id, filename='original.pdf', gdrive_file_id='drive', status='matched', transaction_id='tx', amount=10)
        self.db.add_all([self.transaction, self.invoice])
        self.db.commit()
        with fitz.open() as document:
            document.new_page()
            self.content = document.tobytes()
        self.service = Mock()
        self.mock = patch('web.routers.invoices.get_gdrive_service_for_user', return_value=self.service)
        self.mock.start()

    def tearDown(self):
        self.mock.stop()
        self.db.close()
        self.engine.dispose()

    async def replace(self, content=None, user=None):
        return await replace_invoice_pdf(self.invoice.id, UploadFile(filename='new.pdf', file=BytesIO(self.content if content is None else content)), user or self.user, self.db)

    async def test_replacement_preserves_match_and_refreshes_cache(self):
        self.db.add(PDFCache(user_id=self.user.id, gdrive_file_id='drive', filename='original.pdf', content=b'old', file_size=3))
        self.db.commit()
        result = await self.replace()
        self.assertEqual((result.status, result.transaction_id, result.filename), ('matched', 'tx', 'original.pdf'))
        self.assertEqual(self.db.query(PDFCache).one().content, self.content)
        self.assertEqual(self.transaction.status, 'matched')
        self.service.replace_pdf.assert_called_once_with('drive', self.content)

    async def test_exported_replacement_creates_cache(self):
        self.invoice.status = 'exported'
        self.db.commit()
        result = await self.replace()
        self.assertEqual(result.status, 'exported')
        self.assertEqual(self.db.query(PDFCache).one().content, self.content)

    async def test_invalid_pdf_and_foreign_owner_rejected(self):
        with self.assertRaises(HTTPException) as error:
            await self.replace(b'not PDF')
        self.assertEqual(error.exception.status_code, 400)
        with self.assertRaises(HTTPException) as error:
            await self.replace(user=User(id=999))
        self.assertEqual(error.exception.status_code, 404)
        self.service.replace_pdf.assert_not_called()

    async def test_drive_failure_keeps_local_state(self):
        self.service.replace_pdf.side_effect = RuntimeError('offline')
        with self.assertRaises(HTTPException):
            await self.replace()
        self.assertIsNone(self.invoice.content_sha256)
        self.assertEqual(self.db.query(PDFCache).count(), 0)
        self.assertEqual(self.invoice.transaction_id, 'tx')

    async def test_shared_pdf_rejected(self):
        self.db.add(Invoice(user_id=self.user.id, filename='original.pdf', gdrive_file_id='drive', receipt_index=1))
        self.db.commit()
        with self.assertRaises(HTTPException) as error:
            await self.replace()
        self.assertEqual(error.exception.status_code, 409)
        self.service.replace_pdf.assert_not_called()

    async def test_delete_exported_invoice_and_attachment_unmatches_transaction(self):
        self.invoice.status = 'exported'
        self.db.add(Invoice(user_id=self.user.id, filename='attachment.pdf', gdrive_file_id='attachment', parent_invoice_id=self.invoice.id, attachment_index=1))
        self.db.add(PDFCache(user_id=self.user.id, gdrive_file_id='drive', filename='original.pdf', content=b'old', file_size=3))
        self.db.commit()
        delete_invoice(self.invoice.id, self.user, self.db)
        self.assertEqual(self.db.query(Invoice).count(), 0)
        self.assertEqual(self.db.query(PDFCache).count(), 0)
        self.assertEqual(self.transaction.status, 'unmatched')
        self.assertEqual(self.service.delete_file.call_count, 2)
