"""Send the accountant handoff email through Mailjet."""

import re
from typing import Iterable

import requests

from web.config import settings
from web.database.models import Invoice

DEFAULT_ACCOUNTANT_EMAIL_TEMPLATE = "Posielam doklady za obdobie {period}.\n\n{comments}"
DEFAULT_ACCOUNTANT_EMAIL_SUBJECT_TEMPLATE = (
    "{company_name} - Doklady za obdobie {period}"
)


def build_accountant_email_subject(
    company_name: str,
    year: int,
    month: int,
    template: str = DEFAULT_ACCOUNTANT_EMAIL_SUBJECT_TEMPLATE,
) -> str:
    """Build the accountant subject from its required company and period tokens."""
    normalized_name = company_name.strip()
    if (
        not normalized_name
        or len(normalized_name) > 255
        or "\n" in normalized_name
        or "\r" in normalized_name
    ):
        raise ValueError("Company name is required for the email subject")
    subject_template = template.strip() or DEFAULT_ACCOUNTANT_EMAIL_SUBJECT_TEMPLATE
    if "{company_name}" not in subject_template or "{period}" not in subject_template:
        raise ValueError("Subject template must contain {company_name} and {period}")

    subject = (
        subject_template
        .replace("{company_name}", normalized_name)
        .replace("{period}", f"{month:02d}/{year}")
        .strip()
    )
    if not subject or len(subject) > 255 or "\n" in subject or "\r" in subject:
        raise ValueError("Rendered email subject must be a single line up to 255 characters")
    return subject


def _get_mailjet_sender_records(resource: str) -> list[dict]:
    """Load sender records from one Mailjet REST resource."""
    try:
        response = requests.get(
            f"https://api.mailjet.com/v3/REST/{resource}",
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
    return senders


def _find_active_sender(
    records: Iterable[dict],
    normalized_email: str,
    is_metasender: bool = False,
) -> dict | None:
    """Find an active exact address or wildcard domain record."""
    domain = normalized_email.rsplit("@", 1)[-1]
    domain_match = None
    for sender in records:
        is_active = (
            sender.get("IsEnabled") is True
            if is_metasender
            else str(sender.get("Status", "")).lower() == "active"
        )
        if not is_active:
            continue

        candidate = str(sender.get("Email", "")).strip().lower()
        if candidate == normalized_email:
            return {
                "active": True,
                "scope": "address",
                "matched_sender": candidate,
            }
        if candidate in {domain, f"*@{domain}"}:
            domain_match = candidate

    if domain_match:
        return {"active": True, "scope": "domain", "matched_sender": domain_match}
    return None


def get_mailjet_sender_status(email: str) -> dict:
    """Check active senders and account-wide metasenders in Mailjet."""
    if not settings.mailjet_enabled:
        raise RuntimeError("Mailjet is not configured on the server")

    normalized_email = email.strip().lower()
    sender_match = _find_active_sender(
        _get_mailjet_sender_records("sender"),
        normalized_email,
    )
    if sender_match:
        return sender_match

    metasender_match = _find_active_sender(
        _get_mailjet_sender_records("metasender"),
        normalized_email,
        is_metasender=True,
    )
    if metasender_match:
        return metasender_match

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
    rendered = body_template.replace("{period}", f"{month:02d}/{year}")
    if comment_lines:
        return rendered.replace("{comments}", "\n".join(comment_lines)).strip()

    rendered = re.sub(
        r"(?m)^[^\S\r\n]*\{comments\}[^\S\r\n]*(?:\r?\n|$)",
        "",
        rendered,
    )
    rendered = rendered.replace("{comments}", "")
    rendered = re.sub(r"(?:\r?\n[ \t]*){3,}", "\n\n", rendered)
    return rendered.strip()


def send_accountant_summary(
    recipient: str,
    sender_email: str,
    sender_name: str,
    company_name: str,
    subject_template: str,
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
        "Subject": build_accountant_email_subject(
            company_name,
            year,
            month,
            subject_template,
        ),
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
