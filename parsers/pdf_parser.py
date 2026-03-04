"""Parser for invoice PDF files."""

import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

import pdfplumber

from models.invoice import Invoice


def parse_invoices(directory: Path) -> List[Invoice]:
    """
    Parse all invoice PDFs in a directory.

    Args:
        directory: Directory containing PDF files

    Returns:
        List of Invoice objects
    """
    invoices = []
    pdf_files = list(directory.glob("*.pdf"))

    for pdf_path in pdf_files:
        invoice = parse_invoice_pdf(pdf_path)
        if invoice:
            invoices.append(invoice)

    return invoices


def parse_invoice_pdf(pdf_path: Path) -> Optional[Invoice]:
    """
    Parse a single invoice PDF file.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Invoice object or None if parsing fails
    """
    filename = pdf_path.name

    # Parse filename: YYYY-MM-DD-NNN_type_vendor.pdf
    match = re.match(r"(\d{4}-\d{2}-\d{2})-(\d+)_(\w+)_(.+)\.pdf", filename)
    if not match:
        return None

    date_str, invoice_num, payment_type, vendor = match.groups()

    try:
        invoice_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None

    # Build invoice number from date and sequence
    invoice_number = f"{date_str}-{invoice_num}"

    # Extract amount and VS from PDF content
    amount = None
    vs = None

    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n"

            amount = extract_amount(text)
            vs = extract_vs(text)
    except Exception as e:
        # If PDF parsing fails, continue with filename info only
        pass

    return Invoice(
        file_path=pdf_path,
        invoice_date=invoice_date,
        invoice_number=invoice_number,
        payment_type=payment_type,
        vendor=vendor,
        amount=amount,
        vs=vs
    )


def extract_amount(text: str) -> Optional[Decimal]:
    """
    Extract the total amount from invoice text.

    Args:
        text: Full text extracted from PDF

    Returns:
        Decimal amount or None
    """
    # Look for common total patterns
    patterns = [
        # "Total: 123.45 EUR" or "Total 123,45 EUR"
        r"(?:Total|Celkom|Spolu|TOTAL|Suma|Amount|K\s*(?:ú|u)hrade|Zaplatit|Celkov)[\s:]*([0-9]+[.,][0-9]{2})\s*(?:EUR|€)?",
        # "123.45 EUR" at line end
        r"([0-9]+[.,][0-9]{2})\s*(?:EUR|€)\s*$",
        # Amount with currency first "EUR 123.45"
        r"(?:EUR|€)\s*([0-9]+[.,][0-9]{2})",
        # Bold/emphasized amounts (often totals)
        r"(?:celkem|total|suma).*?([0-9]+[.,][0-9]{2})",
    ]

    amounts = []

    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            try:
                amount_str = match.replace(",", ".")
                amount = Decimal(amount_str)
                if amount > 0:
                    amounts.append(amount)
            except:
                continue

    # Return the largest amount found (usually the total)
    if amounts:
        return max(amounts)

    # Fallback: find any reasonable amount
    all_amounts = re.findall(r"([0-9]+[.,][0-9]{2})", text)
    parsed_amounts = []
    for amt_str in all_amounts:
        try:
            amt = Decimal(amt_str.replace(",", "."))
            if amt > 0:
                parsed_amounts.append(amt)
        except:
            continue

    if parsed_amounts:
        return max(parsed_amounts)

    return None


def extract_vs(text: str) -> Optional[str]:
    """
    Extract Variable Symbol from invoice text.

    Args:
        text: Full text extracted from PDF

    Returns:
        Variable Symbol string or None
    """
    # Common VS patterns
    patterns = [
        r"(?:VS|Variable\s*Symbol|Variabiln(?:ý|i)\s*Symbol)[\s:]*(\d+)",
        r"(?:Invoice|Fakt(?:ú|u)ra)[\s:#]*(\d+)",
        r"(?:Reference|Ref)[\s:#]*(\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)

    return None
