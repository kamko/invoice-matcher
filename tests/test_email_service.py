"""Tests for the Mailjet accountant summary payload."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from web.config import settings
from web.services.email_service import (
    DEFAULT_ACCOUNTANT_EMAIL_SUBJECT_TEMPLATE,
    build_accountant_email_body,
    build_accountant_email_subject,
    get_mailjet_sender_status,
    send_accountant_summary,
)


class AccountantEmailSubjectTests(unittest.TestCase):
    def test_includes_company_name_and_period(self):
        self.assertEqual(
            build_accountant_email_subject("Organization", 2026, 7),
            "Organization - Doklady za obdobie 07/2026",
        )

    def test_rejects_missing_or_multiline_company_name(self):
        for company_name in ("", "   ", "Organization\nName", "x" * 256):
            with self.subTest(company_name=company_name):
                with self.assertRaises(ValueError):
                    build_accountant_email_subject(company_name, 2026, 7)

    def test_supports_editable_subject_template(self):
        self.assertEqual(
            build_accountant_email_subject(
                "Organization",
                2026,
                7,
                "Doklady 07/2026: {company_name} ({period})",
            ),
            "Doklady 07/2026: Organization (07/2026)",
        )

    def test_requires_company_and_period_tokens(self):
        for template in ("Doklady {period}", "{company_name} - Doklady"):
            with self.subTest(template=template):
                with self.assertRaises(ValueError):
                    build_accountant_email_subject(
                        "Organization",
                        2026,
                        7,
                        template,
                    )


class AccountantEmailBodyTests(unittest.TestCase):
    def test_renders_company_name_in_message_template(self):
        result = build_accountant_email_body(
            2026,
            7,
            [],
            "Dobrý deň za {company_name}, obdobie {period}.",
            "Organization",
        )

        self.assertEqual(
            result,
            "Dobrý deň za Organization, obdobie 07/2026.",
        )

    def test_removes_empty_comments_line_without_extra_spacing(self):
        template = (
            "Pekny den,\n\n"
            "Posielam doklady za obdobie {period}.\n\n"
            "{comments}\n\n"
            "S pozdravom,\n\n"
            "kj."
        )

        result = build_accountant_email_body(2026, 7, [], template)

        self.assertEqual(
            result,
            "Pekny den,\n\n"
            "Posielam doklady za obdobie 07/2026.\n\n"
            "S pozdravom,\n\n"
            "kj.",
        )
        self.assertNotIn("{comments}", result)

    def test_keeps_comment_block_when_comments_exist(self):
        invoices = [
            SimpleNamespace(filename="faktura.pdf", comment="Uhradene kartou")
        ]

        result = build_accountant_email_body(
            2026,
            7,
            invoices,
            "Doklady {period}.\n\n{comments}\n\nS pozdravom",
        )

        self.assertIn("Komentáre k dokladom:\n- faktura.pdf: Uhradene kartou", result)


class SendAccountantSummaryTests(unittest.TestCase):
    def setUp(self):
        self.original_api_key = settings.mailjet_api_key
        self.original_secret_key = settings.mailjet_secret_key
        settings.mailjet_api_key = "test-key"
        settings.mailjet_secret_key = "test-secret"

        self.response = Mock()
        self.response.raise_for_status.return_value = None
        self.response.json.return_value = {
            "Messages": [
                {
                    "Status": "success",
                    "To": [{"MessageUUID": "message-123"}],
                }
            ]
        }
        self.response.text = ""
        self.response.status_code = 200

    def tearDown(self):
        settings.mailjet_api_key = self.original_api_key
        settings.mailjet_secret_key = self.original_secret_key

    @patch("web.services.email_service.requests.post")
    def test_sends_edited_body_and_bcc_to_account_email(self, post):
        post.return_value = self.response

        message_id = send_accountant_summary(
            "uctovnik@example.com",
            "doklady@example.com",
            "Moja firma",
            "Organization",
            DEFAULT_ACCOUNTANT_EMAIL_SUBJECT_TEMPLATE,
            2026,
            7,
            [SimpleNamespace(filename="faktura.pdf", comment="Poznamka")],
            body_override="Upraveny text pre tento export",
            bcc_email="ja@example.com",
        )

        message = post.call_args.kwargs["json"]["Messages"][0]
        self.assertEqual(message_id, "message-123")
        self.assertEqual(
            message["Subject"],
            "Organization - Doklady za obdobie 07/2026",
        )
        self.assertEqual(message["TextPart"], "Upraveny text pre tento export")
        self.assertEqual(message["Bcc"], [{"Email": "ja@example.com"}])

    @patch("web.services.email_service.requests.post")
    def test_omits_duplicate_bcc_when_recipient_is_account_email(self, post):
        post.return_value = self.response

        send_accountant_summary(
            "ja@example.com",
            "doklady@example.com",
            "Moja firma",
            "Organization",
            DEFAULT_ACCOUNTANT_EMAIL_SUBJECT_TEMPLATE,
            2026,
            7,
            [],
            body_override="Text",
            bcc_email="JA@example.com",
        )

        message = post.call_args.kwargs["json"]["Messages"][0]
        self.assertNotIn("Bcc", message)


class MailjetSenderStatusTests(unittest.TestCase):
    def setUp(self):
        self.original_api_key = settings.mailjet_api_key
        self.original_secret_key = settings.mailjet_secret_key
        settings.mailjet_api_key = "test-key"
        settings.mailjet_secret_key = "test-secret"

    def tearDown(self):
        settings.mailjet_api_key = self.original_api_key
        settings.mailjet_secret_key = self.original_secret_key

    @staticmethod
    def response(records):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"Data": records}
        response.text = ""
        response.status_code = 200
        return response

    @patch("web.services.email_service.requests.get")
    def test_accepts_active_sender_address(self, get):
        get.return_value = self.response(
            [{"Email": "sender@example.test", "Status": "Active"}]
        )

        result = get_mailjet_sender_status("SENDER@example.test")

        self.assertEqual(
            result,
            {
                "active": True,
                "scope": "address",
                "matched_sender": "sender@example.test",
            },
        )
        self.assertEqual(get.call_count, 1)

    @patch("web.services.email_service.requests.get")
    def test_accepts_enabled_metasender_domain(self, get):
        get.side_effect = [
            self.response([]),
            self.response([{"Email": "*@example.test", "IsEnabled": True}]),
        ]

        result = get_mailjet_sender_status("sender@example.test")

        self.assertEqual(
            result,
            {
                "active": True,
                "scope": "domain",
                "matched_sender": "*@example.test",
            },
        )
        self.assertTrue(get.call_args_list[1].args[0].endswith("/metasender"))
