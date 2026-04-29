"""Parser for invoice PDF files."""

import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

import pdfplumber

from parsers.ekasa_parser import parse_ekasa_pdf


def infer_document_type(
    text: str,
    filename: str,
    payment_type: Optional[str] = None,
    has_wire_fields: bool = False,
    is_ekasa: bool = False,
) -> str:
    """Infer the accountant-facing document type."""
    if is_ekasa:
        return "receipt"

    haystack = f"{filename}\n{text}".lower()

    receipt_keywords = [
        "receipt",
        "blocek",
        "bloček",
        "pokladnicny doklad",
        "pokladničný doklad",
        "paragon",
        "e-kasa",
        "ekasa",
    ]
    other_keywords = [
        "zmluva",
        "contract",
        "bank statement",
        "výpis",
        "vypis",
        "statement",
    ]
    invoice_keywords = [
        "invoice",
        "faktura",
        "faktúra",
        "tax invoice",
        "daňový doklad",
        "danovy doklad",
    ]

    if any(keyword in haystack for keyword in receipt_keywords):
        return "receipt"
    if any(keyword in haystack for keyword in other_keywords):
        return "other"
    if has_wire_fields or any(keyword in haystack for keyword in invoice_keywords):
        return "invoice"
    if payment_type == "cash":
        return "receipt"
    return "invoice"


def _normalize_amount(amount_str: str) -> Optional[Decimal]:
    """
    Normalize amount string to Decimal, handling various formats.

    Handles: 1 647,00 | 1.647,00 | 1,647.00 | 1647.00 | 1647,00
    """
    # Remove spaces and non-breaking spaces
    amount_str = amount_str.replace(" ", "").replace("\u00a0", "").replace("\u202f", "")

    # Determine decimal separator (last comma or period before 2 digits at end)
    if re.match(r".*,\d{2}$", amount_str):
        # European format: 1.234,56 or 1234,56
        amount_str = amount_str.replace(".", "").replace(",", ".")
    elif re.match(r".*\.\d{2}$", amount_str):
        # US format: 1,234.56 or 1234.56
        amount_str = amount_str.replace(",", "")

    try:
        return Decimal(amount_str)
    except:
        return None


def extract_amount(text: str) -> Optional[Decimal]:
    """
    Extract the total amount from invoice text.

    Args:
        text: Full text extracted from PDF

    Returns:
        Decimal amount or None
    """
    # Amount pattern that handles thousands separators (space, dot, comma)
    # Matches: 1 647,00 | 1.647,00 | 1,647.00 | 647.00 | 647,00
    amount_pattern = r"[0-9]+(?:[\s\u00a0\u202f.,][0-9]{3})*[.,][0-9]{2}"

    # Look for common total patterns - prioritize VAT-inclusive amounts
    patterns = [
        # VAT-inclusive patterns FIRST (these should match before generic "Celkom")
        rf"(?:Celkom\s*vrátane\s*DPH|Total\s*(?:with|incl\.?)\s*VAT|Suma\s*s\s*DPH|Celková\s*suma)[:\s(EUR)]*({amount_pattern})",
        # "Total: 1 647,00 EUR" or "Total 1.647,00 EUR"
        rf"(?:Total|Celkom|Spolu|TOTAL|Suma|Amount|K\s*(?:ú|u)hrade|Zaplatit|Celkov)[\s:]*({amount_pattern})\s*(?:EUR|€)?",
        # "EUR 1 647,00" - currency first
        rf"(?:EUR|€)\s*({amount_pattern})",
        # "1 647,00 EUR" at line end
        rf"({amount_pattern})\s*(?:EUR|€)\s*$",
        # Bold/emphasized amounts (often totals)
        rf"(?:celkem|total|suma).*?({amount_pattern})",
    ]

    amounts = []

    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
        for match in matches:
            amount = _normalize_amount(match)
            if amount and amount > 0:
                amounts.append(amount)

    # Return the largest amount found (usually the total)
    if amounts:
        return max(amounts)

    # Fallback: find any reasonable amount
    all_amounts = re.findall(amount_pattern, text)
    parsed_amounts = []
    for amt_str in all_amounts:
        amt = _normalize_amount(amt_str)
        if amt and amt > 0:
            parsed_amounts.append(amt)

    if parsed_amounts:
        return max(parsed_amounts)

    return None


def extract_vs(text: str) -> Optional[str]:
    """
    Extract Variable Symbol from invoice text.

    Args:
        text: Full text extracted from PDF

    Returns:
        Variable Symbol string or None (digits only, slashes removed)
    """
    # Common VS patterns - allow digits, slashes, dashes
    patterns = [
        r"(?:VS|Variable\s*Symbol|Variabiln(?:ý|i)\s*Symbol)[\s:]*([\d/\-]+)",
        r"(?:Invoice|Fakt(?:ú|u)ra)[\s:#]*([\d/\-]+)",
        r"(?:Reference|Ref)[\s:#]*([\d/\-]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            vs = match.group(1)
            # Remove slashes/dashes for payment matching (VS must be numeric)
            vs_clean = re.sub(r"[/\-]", "", vs)
            return vs_clean if vs_clean else None

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

    # Terms that indicate bank/payment info, not vendor
    bank_terms = {'banka', 'bank', 'iban', 'swift', 'pobočka'}

    def is_bank_related(name: str) -> bool:
        name_lower = name.lower()
        return any(term in name_lower for term in bank_terms)

    # Look for common vendor/company patterns
    # Priority 1: Explicit supplier/vendor labels (including Slovak diacritics)
    supplier_patterns = [
        r"(?:Dodávateľ|Dodavatel|Supplier|From|Od)[\s:]*\n?([A-Za-z0-9\s.,&\-éěřťžýáíóúůďňĺľščŕĎŇŤŽÝÁÍÉÚŮĚŘČŠĹĽŔ]+?)(?:\n|IČO|DIČ|$)",
    ]

    for pattern in supplier_patterns:
        match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
        if match:
            vendor = match.group(1).strip()
            if not is_bank_related(vendor) and len(vendor) > 2:
                # Clean up and slugify
                vendor = re.sub(r'[^\w\s-]', '', vendor)
                vendor = re.sub(r'\s+', '-', vendor).lower()[:30]
                if len(vendor) > 2:
                    return vendor

    # Priority 2: Company names with legal suffixes (exclude banks)
    company_pattern = r"([A-Za-z0-9\s.,&\-éěřťžýáíóúůďňĺľščŕĎŇŤŽÝÁÍÉÚŮĚŘČŠĹĽŔ]{2,30}(?:s\.r\.o\.|a\.s\.|Inc|LLC|Ltd|GmbH|Limited))"
    for match in re.finditer(company_pattern, text):
        vendor = match.group(1).strip()
        if not is_bank_related(vendor):
            vendor = re.sub(r'[^\w\s-]', '', vendor)
            vendor = re.sub(r'\s+', '-', vendor).lower()[:30]
            if len(vendor) > 2:
                return vendor

    return None


def _parse_date_from_filename(filename: str) -> Optional[datetime]:
    """
    Try to extract date from filename convention: YYYY-MM-DD-NNN_type_vendor.pdf

    Returns datetime object or None if filename doesn't match pattern.
    """
    match = re.match(r"(\d{4}-\d{2}-\d{2})-\d+_", filename)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d")
        except ValueError:
            pass
    return None


def parse_uploaded_pdf(pdf_path: Path) -> dict:
    """
    Parse an uploaded PDF file.

    Date extraction priority: filename -> LLM -> naive regex -> error

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Dict with extracted data, or raises ValueError if date cannot be determined
    """
    filename = pdf_path.name
    result = {
        'vendor': None,
        'document_type': 'invoice',
        'amount': None,
        'currency': 'EUR',  # Default to EUR
        'invoice_date': None,
        'payment_type': 'card',  # Default to card
        'vs': None,
        'iban': None,
        'is_credit_note': False,
    }

    # 1. Try to parse date from filename FIRST
    filename_date = _parse_date_from_filename(filename)
    if filename_date:
        result['invoice_date'] = filename_date.date()
        # Also extract payment_type and vendor from filename if present
        match = re.match(r"\d{4}-\d{2}-\d{2}-\d+_([a-zA-Z0-9-]+)_(.+)\.pdf", filename)
        if match:
            result['payment_type'] = match.group(1)
            result['vendor'] = match.group(2).replace("-", " ").title()

    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n"

            # If no text extracted (scanned image), try e-kasa QR parsing
            if not text.strip():
                ekasa_receipt = parse_ekasa_pdf(pdf_path)
                if ekasa_receipt:
                    return {
                        'vendor': ekasa_receipt.vendor_name,
                        'document_type': 'receipt',
                        'amount': ekasa_receipt.total_price,
                        'invoice_date': ekasa_receipt.issue_date.date(),
                        'payment_type': 'card',
                        'vs': None,
                        'iban': None,
                        'is_credit_note': False,
                    }
                # No text and no e-kasa, but we might have filename date
                if result['invoice_date']:
                    result['document_type'] = infer_document_type(
                        "",
                        filename,
                        payment_type=result['payment_type'],
                    )
                    return result
                raise ValueError(f"Cannot extract date from image PDF: {filename}")

            # 2. Try LLM extraction (for amount, currency, vs, vendor, and date if needed)
            llm_date = None
            try:
                from parsers.llm_extractor import extract_invoice_data_llm
                llm_data = extract_invoice_data_llm(text)
                if llm_data.get("amount"):
                    result['amount'] = llm_data["amount"]
                if llm_data.get("currency"):
                    result['currency'] = llm_data["currency"]
                if llm_data.get("vs"):
                    result['vs'] = llm_data["vs"]
                if llm_data.get("iban"):
                    result['iban'] = llm_data["iban"]
                if llm_data.get("vendor") and not result['vendor']:
                    result['vendor'] = llm_data["vendor"]
                if llm_data.get("date"):
                    llm_date = llm_data["date"]
            except Exception:
                pass

            # 3. Fallback to regex if LLM didn't extract
            if result['amount'] is None:
                result['amount'] = extract_amount(text)
            if result['vs'] is None:
                result['vs'] = extract_vs(text)
            if result['vendor'] is None:
                result['vendor'] = extract_vendor(text)

            # Date priority: filename (already set) -> LLM -> naive regex
            if result['invoice_date'] is None:
                if llm_date:
                    result['invoice_date'] = llm_date
                else:
                    naive_date = extract_date(text)
                    if naive_date:
                        result['invoice_date'] = naive_date.date()

            # If no amount found in text, try e-kasa as fallback
            if result['amount'] is None:
                ekasa_receipt = parse_ekasa_pdf(pdf_path)
                if ekasa_receipt:
                    result['amount'] = ekasa_receipt.total_price
                    if result['invoice_date'] is None:
                        result['invoice_date'] = ekasa_receipt.issue_date.date()
                    if result['vendor'] is None:
                        result['vendor'] = ekasa_receipt.vendor_name
                    result['document_type'] = 'receipt'

            # 4. If still no date, raise error
            if result['invoice_date'] is None:
                raise ValueError(f"Cannot determine invoice date for: {filename}")

            # Detect wire transfer from content
            if result['iban'] or result['vs']:
                result['payment_type'] = 'wire'

            if result['document_type'] != 'receipt':
                result['document_type'] = infer_document_type(
                    text,
                    filename,
                    payment_type=result['payment_type'],
                    has_wire_fields=bool(result['iban'] or result['vs']),
                )

            return result

    except ValueError:
        raise
    except Exception as e:
        # Try e-kasa as last resort
        try:
            ekasa_receipt = parse_ekasa_pdf(pdf_path)
            if ekasa_receipt:
                return {
                    'vendor': ekasa_receipt.vendor_name,
                    'document_type': 'receipt',
                    'amount': ekasa_receipt.total_price,
                    'invoice_date': ekasa_receipt.issue_date.date(),
                    'payment_type': 'card',
                    'vs': None,
                    'iban': None,
                    'is_credit_note': False,
                }
        except Exception:
            pass

        # If we have filename date, return with that
        if result['invoice_date']:
            result['document_type'] = infer_document_type(
                "",
                filename,
                payment_type=result['payment_type'],
                has_wire_fields=bool(result['iban'] or result['vs']),
            )
            return result

        raise ValueError(f"Failed to parse PDF {filename}: {e}")
