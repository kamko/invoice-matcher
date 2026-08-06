"""Tests for the Mailjet accountant summary payload."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from web.config import settings
from web.services.email_service import get_mailjet_sender_status, send_accountant_summary


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
            2026,
            7,
            [SimpleNamespace(filename="faktura.pdf", comment="Poznamka")],
            body_override="Upraveny text pre tento export",
            bcc_email="ja@example.com",
        )

        message = post.call_args.kwargs["json"]["Messages"][0]
        self.assertEqual(message_id, "message-123")
        self.assertEqual(message["TextPart"], "Upraveny text pre tento export")
        self.assertEqual(message["Bcc"], [{"Email": "ja@example.com"}])

    @patch("web.services.email_service.requests.post")
    def test_omits_duplicate_bcc_when_recipient_is_account_email(self, post):
        post.return_value = self.response

        send_accountant_summary(
            "ja@example.com",
            "doklady@example.com",
            "Moja firma",
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
            [{"Email": "info@kamko.group", "Status": "Active"}]
        )

        result = get_mailjet_sender_status("INFO@kamko.group")

        self.assertEqual(
            result,
            {
                "active": True,
                "scope": "address",
                "matched_sender": "info@kamko.group",
            },
        )
        self.assertEqual(get.call_count, 1)

    @patch("web.services.email_service.requests.get")
    def test_accepts_enabled_metasender_domain(self, get):
        get.side_effect = [
            self.response([]),
            self.response([{"Email": "*@kamko.group", "IsEnabled": True}]),
        ]

        result = get_mailjet_sender_status("info@kamko.group")

        self.assertEqual(
            result,
            {
                "active": True,
                "scope": "domain",
                "matched_sender": "*@kamko.group",
            },
        )
        self.assertTrue(get.call_args_list[1].args[0].endswith("/metasender"))
