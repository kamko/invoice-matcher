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


def extract_date(text: str) -> Optional[datetime]:
    """Extract invoice date from text."""
    MONTHS = {
        'january': 1, 'jan': 1,
        'february': 2, 'feb': 2,
        'march': 3, 'mar': 3,
        'april': 4, 'apr': 4,
        'may': 5,
        'june': 6, 'jun': 6,
        'july': 7, 'jul': 7,
        'august': 8, 'aug': 8,
        'september': 9, 'sep': 9, 'sept': 9,
        'october': 10, 'oct': 10,
        'november': 11, 'nov': 11,
        'december': 12, 'dec': 12,
    }

    # Try month name patterns first (e.g., "February 6, 2026" or "Feb 6, 2026")
    month_pattern = r"(?:Date\s+(?:of\s+)?issue|Issue\s+date|Date)[\s:]*([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})"
    match = re.search(month_pattern, text, re.IGNORECASE)
    if match:
        month_str, day, year = match.groups()
        month = MONTHS.get(month_str.lower())
        if month:
            try:
                return datetime(int(year), month, int(day))
            except ValueError:
                pass

    # Fallback: any month name followed by day, year
    general_month_pattern = r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})"
    for match in re.finditer(general_month_pattern, text):
        month_str, day, year = match.groups()
        month = MONTHS.get(month_str.lower())
        if month:
            try:
                return datetime(int(year), month, int(day))
            except ValueError:
                continue

    # Common date patterns
    patterns = [
        # DD.MM.YYYY or DD/MM/YYYY
        (r"(?:Date|Datum|Issue|Vystavení)[\s:]*(\d{1,2})[./](\d{1,2})[./](\d{4})", "dmy"),
        # YYYY-MM-DD
        (r"(?:Date|Datum|Issue)[\s:]*(\d{4})-(\d{2})-(\d{2})", "ymd"),
        # Any date DD.MM.YYYY
        (r"(\d{1,2})[./](\d{1,2})[./](\d{4})", "dmy"),
    ]

    for pattern, fmt in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                if fmt == "dmy":
                    d, m, y = match.groups()
                    return datetime(int(y), int(m), int(d))
                elif fmt == "ymd":
                    y, m, d = match.groups()
                    return datetime(int(y), int(m), int(d))
            except (ValueError, TypeError):
                continue

    return None


def extract_vendor(text: str) -> Optional[str]:
    """Extract vendor name from text."""
    # Known vendor patterns - add common ones
    known_vendors = {
        'openai': 'openai',
        'chatgpt': 'openai',
        'google': 'google',
        'hetzner': 'hetzner',
        'cloudflare': 'cloudflare',
        'amazon': 'amazon',
        'aws': 'aws',
        'microsoft': 'microsoft',
        'azure': 'azure',
        'digitalocean': 'digitalocean',
        'github': 'github',
        'slack': 'slack',
        'zoom': 'zoom',
        'dropbox': 'dropbox',
        'notion': 'notion',
        'figma': 'figma',
        'vercel': 'vercel',
        'netlify': 'netlify',
        'heroku': 'heroku',
        'stripe': 'stripe',
    }

    text_lower = text.lower()
    for keyword, vendor in known_vendors.items():
        if keyword in text_lower:
            return vendor

    # Look for common vendor/company patterns
    patterns = [
        r"(?:From|Od|Dodavatel|Supplier|Company)[\s:]*([A-Za-z0-9\s.,&-]+?)(?:\n|$)",
        r"^([A-Z][A-Za-z0-9\s.,&-]{2,30}(?:s\.r\.o\.|a\.s\.|Inc|LLC|Ltd|GmbH|Limited))",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            vendor = match.group(1).strip()
            # Clean up and slugify
            vendor = re.sub(r'[^\w\s-]', '', vendor)
            vendor = re.sub(r'\s+', '-', vendor).lower()[:30]
            if len(vendor) > 2:
                return vendor

    return None


def parse_uploaded_pdf(pdf_path: Path) -> Optional[Invoice]:
    """
    Parse an uploaded PDF file (without filename convention).

    Extracts all info from PDF content.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Invoice object or None if parsing fails
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n"

            if not text.strip():
                return None

            # Extract data from content
            amount = extract_amount(text)
            vs = extract_vs(text)
            invoice_date_dt = extract_date(text)
            vendor = extract_vendor(text)

            # Use today if no date found
            if invoice_date_dt:
                invoice_date = invoice_date_dt.date()
            else:
                invoice_date = datetime.now().date()

            # Generate invoice number from VS or filename
            invoice_number = vs or pdf_path.stem

            return Invoice(
                file_path=pdf_path,
                invoice_date=invoice_date,
                invoice_number=invoice_number,
                payment_type="unknown",
                vendor=vendor or "unknown",
                amount=amount,
                vs=vs
            )

    except Exception as e:
        return None
