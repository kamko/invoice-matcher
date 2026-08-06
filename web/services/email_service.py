"""Send the accountant handoff email through Mailjet."""

from typing import Iterable

import requests

from web.config import settings
from web.database.models import Invoice


def build_accountant_email_body(year: int, month: int, invoices: Iterable[Invoice]) -> str:
    """Build the deliberately short Slovak export summary."""
    lines = [f"Posielam doklady za obdobie {month:02d}/{year}."]
    comments = [
        (invoice.filename, invoice.comment.strip())
        for invoice in invoices
        if invoice.comment and invoice.comment.strip()
    ]

    if comments:
        lines.extend(["", "Komentáre k dokladom:"])
        for filename, comment in comments:
            normalized_comment = " ".join(comment.splitlines())
            lines.append(f"- {filename}: {normalized_comment}")

    return "\n".join(lines)


def send_accountant_summary(
    recipient: str,
    year: int,
    month: int,
    invoices: Iterable[Invoice],
) -> str:
    """Send the period summary and return the Mailjet message id."""
    if not settings.mailjet_enabled:
        raise RuntimeError("Mailjet is not configured on the server")

    response = requests.post(
        "https://api.mailjet.com/v3.1/send",
        auth=(settings.mailjet_api_key, settings.mailjet_secret_key),
        json={
            "Messages": [
                {
                    "From": {
                        "Email": settings.mailjet_sender_email,
                        "Name": settings.mailjet_sender_name,
                    },
                    "To": [{"Email": recipient}],
                    "Subject": f"Doklady za obdobie {month:02d}/{year}",
                    "TextPart": build_accountant_email_body(year, month, invoices),
                }
            ]
        },
        timeout=20,
    )

    try:
        response.raise_for_status()
        result = response.json()
        message = result["Messages"][0]
        if message.get("Status") != "success":
            raise RuntimeError(str(message.get("Errors") or "Mailjet rejected the email"))
        recipient_result = message["To"][0]
        return str(recipient_result.get("MessageUUID") or recipient_result["MessageID"])
    except (KeyError, ValueError, requests.HTTPError) as exc:
        details = response.text.strip()[:500]
        raise RuntimeError(f"Mailjet send failed: {details or response.status_code}") from exc
