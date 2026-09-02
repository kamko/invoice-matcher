"""Tests for PDF document-role detection."""

import unittest

from parsers.pdf_parser import is_supporting_attachment


class SupportingAttachmentDetectionTests(unittest.TestCase):
    def test_detects_orlen_attachment_from_pdf_metadata(self):
        self.assertTrue(is_supporting_attachment(
            "Prehľad pohľadávok a záväzkov",
            {"Title": "014_InvoiceAttachment_ClaimAndObligation"},
        ))

    def test_detects_attachment_from_visible_heading(self):
        self.assertTrue(is_supporting_attachment(
            "Príloha k daňovému dokladu č. 7961010963",
        ))

    def test_does_not_treat_invoice_mentioning_an_attachment_as_attachment(self):
        self.assertFalse(is_supporting_attachment(
            "Faktúra. Neoddeliteľnou súčasťou daňového dokladu je príloha.",
            {"Title": "012_BusinessInvoice"},
        ))


if __name__ == "__main__":
    unittest.main()
