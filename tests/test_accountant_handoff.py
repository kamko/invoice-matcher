"""Payment-first exports, manual status, and recoverable accountant emails."""

import asyncio
import io
import unittest
import zipfile
from datetime import date
from unittest.mock import Mock, patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web.database.models import Base, Invoice, PDFCache, Transaction, User, UserSetting
from web.routers.dashboard import (
    CopyToAccountantRequest, _get_exportable_invoices,
    copy_to_accountant_folder, export_month, get_accountant_email_preview,
)
from web.routers.invoices import list_invoices, update_invoice
from web.schemas.invoices import InvoiceUpdate
from web.services.matching_service import MatchingService


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.user = User(google_sub='owner', email='owner@example.com')
        self.db.add(self.user)
        self.db.commit()
        for key, value in [('company_name', 'Test Company'), ('accountant_email', 'accountant@example.com'), ('mailjet_sender_email', 'sender@example.com')]:
            self.db.add(UserSetting(user_id=self.user.id, key=key, value=value))
        self.db.commit()
        self.drive = Mock()
        self.drive.find_or_create_subfolder.side_effect = lambda root, name: name
        self.drive.list_files_in_folder.return_value = []
        self.drive.download_file.return_value = b'%PDF-test'
        self.patches = [
            patch('web.routers.dashboard.get_gdrive_service_for_user', return_value=self.drive),
            patch('web.routers.dashboard.settings', mailjet_enabled=True),
            patch('web.routers.dashboard.get_mailjet_sender_status', return_value={'active': True}),
            patch('web.routers.dashboard.send_accountant_summary', return_value='message-1'),
        ]
        self.mocks = [p.start() for p in self.patches]
        self.send = self.mocks[-1]

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.db.close()
        self.engine.dispose()

    def invoice(self, name='one', comment=None, paired=True, **values):
        if paired:
            self.db.add(Transaction(id=name, user_id=self.user.id, date=date(2026, 8, 10), amount=-10, type='expense', status='matched'))
        fields = dict(user_id=self.user.id, filename=f'{name}.pdf', gdrive_file_id=name,
                      invoice_date=date(2026, 8, 1), status='matched' if paired else 'unmatched',
                      transaction_id=name if paired else None, include_in_export=True,
                      comment=comment, payment_type='card')
        fields.update(values)
        invoice = Invoice(**fields)
        self.db.add(invoice)
        self.db.commit()
        return invoice

    def handoff(self, **kwargs):
        return copy_to_accountant_folder('2026-08', 'accountant-root', True,
                                        CopyToAccountantRequest(**kwargs), self.user, self.db)

    def test_progressive_without_notes_needs_no_email_configuration(self):
        invoice = self.invoice()
        with patch('web.routers.dashboard.settings', mailjet_enabled=False):
            result = self.handoff()
        self.assertEqual(result['copied'], 1)
        self.assertEqual(result['email']['status'], 'not_requested')
        self.assertEqual(invoice.status, 'exported')
        self.send.assert_not_called()
        with self.assertRaises(HTTPException):
            self.handoff()
        self.assertEqual(self.drive.copy_file.call_count, 1)

    def test_only_real_pairs_are_exportable_in_both_views(self):
        valid = self.invoice()
        self.invoice('cash', paired=False, status='cash')
        self.invoice('orphan', paired=False, status='matched')
        self.invoice('internal', include_in_export=False)
        self.invoice('exported', status='exported')
        self.invoice('different-month', invoice_date=date(2026, 7, 1))
        selected = _get_exportable_invoices(self.db, self.user.id, 2026, 8)
        listed = list_invoices('2026-08', 'exportable', None, self.user, self.db)
        self.assertEqual([i.id for i in selected], [valid.id])
        self.assertEqual([i.id for i in listed.invoices], [valid.id])

    def test_notes_are_only_sent_at_completion_and_email_can_retry(self):
        invoice = self.invoice(comment='Please check this amount')
        result = self.handoff()
        self.assertEqual(result['email']['status'], 'not_requested')
        self.assertEqual(invoice.status, 'exported')
        self.send.assert_not_called()
        self.invoice('manual', paired=False, status='exported', comment='Handed over manually')
        self.send.side_effect = RuntimeError('mail offline')
        result = self.handoff(complete_month=True)
        self.assertEqual(result['email']['status'], 'failed')
        self.send.side_effect = None
        result = self.handoff(complete_month=True)
        self.assertEqual(result['copied'], 0)
        self.assertEqual(result['email']['status'], 'sent')
        self.assertEqual(self.drive.copy_file.call_count, 1)
        self.assertIn('one.pdf', self.send.call_args.kwargs['body_override'])
        self.assertIn('manual.pdf', self.send.call_args.kwargs['body_override'])

    def test_complete_empty_remainder_sends_confirmation(self):
        self.invoice(status='exported')
        result = self.handoff(complete_month=True)
        self.assertEqual(result['copied'], 0)
        self.assertEqual(result['email']['status'], 'sent')
        self.assertIn('Všetky doklady', self.send.call_args.kwargs['body_override'])

    def test_failed_copy_never_sends_completion_and_retry_copies_only_remainder(self):
        good = self.invoice('good')
        bad = self.invoice('bad')
        self.drive.copy_file.side_effect = [None, RuntimeError('offline')]
        result = self.handoff(complete_month=True)
        self.send.assert_not_called()
        self.assertEqual(result['email']['status'], 'failed')
        self.assertEqual(good.status, 'exported')
        self.assertEqual(bad.status, 'matched')
        self.drive.copy_file.side_effect = None
        result = self.handoff(complete_month=True)
        self.assertEqual(result['copied'], 1)
        self.assertEqual(result['email']['status'], 'sent')

    def test_unmatched_expenses_require_review_but_known_and_skipped_do_not(self):
        for state in ['known', 'skipped', 'unmatched']:
            self.db.add(Transaction(id=state, user_id=self.user.id, date=date(2026, 8, 3), amount=-10, type='expense', status=state))
        self.db.commit()
        preview = get_accountant_email_preview('2026-08', self.user, self.db, True)
        self.assertEqual(preview['unmatched_expenses'], 1)
        with self.assertRaises(HTTPException) as caught:
            self.handoff(complete_month=True)
        self.assertEqual(caught.exception.status_code, 409)
        self.send.assert_not_called()
        self.assertEqual(self.handoff(complete_month=True, acknowledge_unmatched=True)['email']['status'], 'sent')

    def test_manual_export_toggle_preserves_payment_link(self):
        invoice = self.invoice()
        update_invoice(invoice.id, InvoiceUpdate(exported=True), self.user, self.db)
        self.assertEqual(invoice.status, 'exported')
        self.assertEqual(invoice.transaction_id, 'one')
        update_invoice(invoice.id, InvoiceUpdate(exported=False), self.user, self.db)
        self.assertEqual(invoice.status, 'matched')
        self.assertEqual(invoice.transaction_id, 'one')
        self.drive.copy_file.assert_not_called()
        self.send.assert_not_called()

    def test_unmatch_and_rematch_does_not_reset_export_status(self):
        invoice = self.invoice(status='exported')
        service = MatchingService(self.db, self.user.id)
        service.unmatch_invoice(invoice.id)
        self.assertEqual(invoice.status, 'exported')
        service.match_invoice_to_transaction(invoice.id, 'one', learn_alias=False)
        self.assertEqual(invoice.status, 'exported')
        self.assertEqual(invoice.transaction_id, 'one')

    def test_manual_unexport_without_payment_does_not_invent_match(self):
        invoice = self.invoice(paired=False, status='exported')
        update_invoice(invoice.id, InvoiceUpdate(exported=False), self.user, self.db)
        self.assertEqual(invoice.status, 'unmatched')

    def test_statement_failure_withholds_completion(self):
        self.invoice()
        with patch('web.routers.dashboard.fetch_monthly_statement_pdf', side_effect=RuntimeError('offline')):
            result = self.handoff(complete_month=True, include_monthly_statement=True, fio_token='test')
        self.assertEqual(result['statement']['status'], 'failed')
        self.send.assert_not_called()

    def test_user_scope_and_missing_pdf(self):
        invoice = self.invoice(gdrive_file_id=None)
        with self.assertRaises(HTTPException):
            self.handoff(complete_month=True)
        self.send.assert_not_called()
        other = User(google_sub='other', email='other@example.com')
        self.db.add(other)
        self.db.commit()
        with self.assertRaises(HTTPException) as caught:
            update_invoice(invoice.id, InvoiceUpdate(exported=True), other, self.db)
        self.assertEqual(caught.exception.status_code, 404)

    def test_zip_marks_only_files_actually_in_archive(self):
        good = self.invoice('good')
        bad = self.invoice('bad')
        self.invoice('previous', status='exported')
        self.drive.download_file.side_effect = [b'%PDF-good', RuntimeError('offline')]
        response = export_month('2026-08', True, self.user, self.db)
        async def body():
            return b''.join([chunk async for chunk in response.body_iterator])
        with zipfile.ZipFile(io.BytesIO(asyncio.run(body()))) as archive:
            self.assertEqual(archive.namelist(), ['good.pdf'])
        self.assertEqual(good.status, 'exported')
        self.assertEqual(bad.status, 'matched')


if __name__ == '__main__':
    unittest.main()
