"""Send the accountant handoff email through Mailjet."""

from typing import Iterable

import requests

from web.config import settings
from web.database.models import Invoice

DEFAULT_ACCOUNTANT_EMAIL_TEMPLATE = "Posielam doklady za obdobie {period}.\n\n{comments}"


def get_mailjet_sender_status(email: str) -> dict:
    """Check whether an exact sender or its whole domain is active in Mailjet."""
    if not settings.mailjet_enabled:
        raise RuntimeError("Mailjet is not configured on the server")

    normalized_email = email.strip().lower()
    domain = normalized_email.rsplit("@", 1)[-1]
    try:
        response = requests.get(
            "https://api.mailjet.com/v3/REST/sender",
            auth=(settings.mailjet_api_key, settings.mailjet_secret_key),
            params={"Limit": 100},
            timeout=20,
        )
    except requests.RequestException as exc:
        raise RuntimeError("Mailjet sender check failed: network error") from exc

    try:
        response.raise_for_status()
        senders = response.json().get("Data", [])
    except (ValueError, requests.HTTPError) as exc:
        details = response.text.strip()[:500]
        raise RuntimeError(
            f"Mailjet sender check failed: {details or response.status_code}"
        ) from exc

    exact_match = None
    domain_match = None
    for sender in senders:
        if str(sender.get("Status", "")).lower() != "active":
            continue
        candidate = str(sender.get("Email", "")).strip().lower()
        if candidate == normalized_email:
            exact_match = candidate
            break
        if candidate in {domain, f"*@{domain}"}:
            domain_match = candidate

    if exact_match:
        return {"active": True, "scope": "address", "matched_sender": exact_match}
    if domain_match:
        return {"active": True, "scope": "domain", "matched_sender": domain_match}
    return {"active": False, "scope": None, "matched_sender": None}


def build_accountant_email_body(
    year: int,
    month: int,
    invoices: Iterable[Invoice],
    template: str = DEFAULT_ACCOUNTANT_EMAIL_TEMPLATE,
) -> str:
    """Build the deliberately short Slovak export summary."""
    comments = [
        (invoice.filename, invoice.comment.strip())
        for invoice in invoices
        if invoice.comment and invoice.comment.strip()
    ]

    comment_lines = []
    if comments:
        comment_lines.append("Komentáre k dokladom:")
        for filename, comment in comments:
            normalized_comment = " ".join(comment.splitlines())
            comment_lines.append(f"- {filename}: {normalized_comment}")

    body_template = template.strip() or DEFAULT_ACCOUNTANT_EMAIL_TEMPLATE
    return (
        body_template
        .replace("{period}", f"{month:02d}/{year}")
        .replace("{comments}", "\n".join(comment_lines))
        .strip()
    )


def send_accountant_summary(
    recipient: str,
    sender_email: str,
    sender_name: str,
    year: int,
    month: int,
    invoices: Iterable[Invoice],
    template: str = DEFAULT_ACCOUNTANT_EMAIL_TEMPLATE,
    body_override: str | None = None,
    bcc_email: str | None = None,
) -> str:
    """Send the period summary and return the Mailjet message id."""
    if not settings.mailjet_enabled:
        raise RuntimeError("Mailjet is not configured on the server")

    message = {
        "From": {
            "Email": sender_email,
            "Name": sender_name,
        },
        "To": [{"Email": recipient}],
        "Subject": f"Doklady za obdobie {month:02d}/{year}",
        "TextPart": (
            body_override.strip()
            if body_override and body_override.strip()
            else build_accountant_email_body(year, month, invoices, template)
        ),
    }
    if bcc_email and bcc_email.strip().lower() != recipient.strip().lower():
        message["Bcc"] = [{"Email": bcc_email.strip()}]

    response = requests.post(
        "https://api.mailjet.com/v3.1/send",
        auth=(settings.mailjet_api_key, settings.mailjet_secret_key),
        json={"Messages": [message]},
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
