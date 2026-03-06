"""Parser for invoice PDF files."""

import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

import pdfplumber

from models.invoice import Invoice
from parsers.ekasa_parser import parse_ekasa_pdf


def parse_invoices(directory: Path) -> List[Invoice]:
    """
    Parse all invoice PDFs in a directory.

    For multi-receipt PDFs (e.g., combined e-kasa receipts), returns
    multiple Invoice objects for the same file, one per receipt.

    Args:
        directory: Directory containing PDF files

    Returns:
        List of Invoice objects
    """
    invoices = []
    pdf_files = list(directory.glob("*.pdf"))

    for pdf_path in pdf_files:
        parsed = parse_invoice_pdf_multi(pdf_path)
        invoices.extend(parsed)

    return invoices


def parse_invoice_pdf_multi(pdf_path: Path) -> List[Invoice]:
    """
    Parse a PDF file, returning multiple Invoice objects if it contains multiple receipts.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        List of Invoice objects (usually 1, but can be more for multi-receipt PDFs)
    """
    filename = pdf_path.name

    # Parse filename: YYYY-MM-DD-NNN_type_vendor.pdf
    match = re.match(r"(\d{4}-\d{2}-\d{2})-(\d+)_([a-zA-Z0-9-]+)_(.+)\.pdf", filename)
    if not match:
        return []

    date_str, invoice_num, payment_type, vendor = match.groups()

    try:
        invoice_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return []

    invoice_number = f"{date_str}-{invoice_num}"

    # Check if it's a text PDF or image PDF
    page_texts = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                page_texts.append(page_text)
    except Exception:
        pass

    text = "\n".join(page_texts)
    text_has_content = len(text.strip()) > 50

    if text_has_content:
        # TEXT PDF - check if multi-page with separate receipts per page
        if len(page_texts) > 1:
            # Check if each page looks like a separate receipt (has amount pattern)
            # Handle negative amounts for credit notes: "Celkom: -18,88 EUR"
            # Prioritize VAT-inclusive patterns
            amount_pattern_vat = re.compile(r"(?:Celkom\s*vrátane\s*DPH|Total\s*(?:with|incl\.?)\s*VAT|Suma\s*s\s*DPH)[:\s(EUR)]*(-?\d+[.,]\d{2})", re.IGNORECASE)
            amount_pattern = re.compile(r"(?:Cena|Suma|Total|Amount|Celkom)[:\s]*(-?\d+[.,]\d{2})\s*(?:EUR|€|\$)?", re.IGNORECASE)
            # Credit note detection patterns (Slovak)
            credit_note_patterns = [
                r"Opravný\s+daňový\s+doklad",  # Corrective tax document
                r"Dobropis",  # Credit note
                r"Credit\s+Note",
                r"Storno",  # Cancellation
            ]
            credit_note_regex = re.compile("|".join(credit_note_patterns), re.IGNORECASE)

            page_amounts = []
            page_is_credit_note = []
            for page_text in page_texts:
                # Check amount - prefer VAT-inclusive pattern first
                match = amount_pattern_vat.search(page_text)
                if not match:
                    match = amount_pattern.search(page_text)
                if match:
                    amt_str = match.group(1).replace(",", ".")
                    page_amounts.append(Decimal(amt_str))
                else:
                    page_amounts.append(None)
                # Check if this page is a credit note
                is_cn = bool(credit_note_regex.search(page_text))
                page_is_credit_note.append(is_cn)

            # If multiple pages have amounts, treat as multi-receipt
            valid_amounts = [a for a in page_amounts if a is not None]
            if len(valid_amounts) > 1:
                invoices = []
                for i, amount in enumerate(page_amounts):
                    if amount is not None:
                        inv = Invoice(
                            file_path=pdf_path,
                            invoice_date=invoice_date,
                            invoice_number=f"{invoice_number}-{i+1}",
                            payment_type=payment_type,
                            vendor=vendor,
                            amount=amount,
                            vs=None,
                            receipt_index=i,
                            _is_credit_note=page_is_credit_note[i]
                        )
                        invoices.append(inv)
                if invoices:
                    cn_count = sum(1 for inv in invoices if inv.is_credit_note)
                    inv_count = len(invoices) - cn_count
                    print(f"Multi-page text PDF: {filename} -> {inv_count} invoices, {cn_count} credit notes")
                    return invoices

        # Single page or single receipt - use existing logic
        invoice = parse_invoice_pdf(pdf_path)
        return [invoice] if invoice else []

    # IMAGE PDF - might have multiple receipts
    # Try to extract all receipts using LLM vision
    try:
        from parsers.llm_extractor import extract_all_receipts_from_image
        receipts = extract_all_receipts_from_image(pdf_path)

        if receipts and len(receipts) > 0:
            invoices = []
            for i, receipt in enumerate(receipts):
                # Create invoice for each receipt
                inv = Invoice(
                    file_path=pdf_path,
                    invoice_date=invoice_date,
                    invoice_number=f"{invoice_number}-{i+1}" if len(receipts) > 1 else invoice_number,
                    payment_type=payment_type,
                    vendor=receipt.get("vendor") or vendor,
                    amount=receipt.get("amount"),
                    vs=None,
                    receipt_index=i
                )
                invoices.append(inv)

            if len(receipts) > 1:
                print(f"Multi-receipt PDF: {filename} -> {len(receipts)} invoices")

            return invoices
    except Exception as e:
        print(f"Multi-receipt extraction failed for {filename}: {e}")

    # Fallback to single invoice parsing
    invoice = parse_invoice_pdf(pdf_path)
    return [invoice] if invoice else []


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
    # Note: type can contain hyphens (e.g., sepa-debit, credit-note)
    match = re.match(r"(\d{4}-\d{2}-\d{2})-(\d+)_([a-zA-Z0-9-]+)_(.+)\.pdf", filename)
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

    # 1. Try PDF text extraction
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n"
    except Exception:
        pass

    text_has_content = len(text.strip()) > 50  # More than just whitespace/headers

    if text_has_content:
        # TEXT PDF (invoice): LLM text -> regex

        # Try LLM text extraction (cheap, accurate)
        try:
            from parsers.llm_extractor import extract_invoice_data_llm
            llm_data = extract_invoice_data_llm(text)
            if llm_data.get("amount"):
                amount = llm_data["amount"]
            if llm_data.get("vs"):
                vs = llm_data["vs"]
        except Exception:
            pass

        # Fallback to regex
        if amount is None:
            amount = extract_amount(text)
        if vs is None:
            vs = extract_vs(text)

    else:
        # IMAGE PDF FLOW: e-kasa -> LLM vision

        # 3a. Try e-kasa QR first (FREE)
        try:
            from parsers.ekasa_parser import parse_ekasa_pdf
            ekasa_receipt = parse_ekasa_pdf(pdf_path)
            if ekasa_receipt:
                amount = ekasa_receipt.total_price
        except Exception:
            pass

        # 3b. If e-kasa didn't work, use LLM vision (expensive)
        if amount is None or vs is None:
            try:
                from parsers.llm_extractor import extract_invoice_data_from_image
                llm_data = extract_invoice_data_from_image(pdf_path)
                if amount is None and llm_data.get("amount"):
                    amount = llm_data["amount"]
                if vs is None and llm_data.get("vs"):
                    vs = llm_data["vs"]
            except Exception:
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


def parse_uploaded_pdf(pdf_path: Path) -> Optional[Invoice]:
    """
    Parse an uploaded PDF file (without filename convention).

    Extracts all info from PDF content. For scanned receipts,
    tries to extract QR code and fetch data from e-kasa API.

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

            # If no text extracted (scanned image), try e-kasa QR parsing
            if not text.strip():
                ekasa_receipt = parse_ekasa_pdf(pdf_path)
                if ekasa_receipt:
                    return Invoice(
                        file_path=pdf_path,
                        invoice_date=ekasa_receipt.issue_date.date(),
                        invoice_number=ekasa_receipt.receipt_id,
                        payment_type="card",
                        vendor=ekasa_receipt.vendor_name,
                        amount=ekasa_receipt.total_price,
                        vs=None
                    )
                return None

            # Try LLM extraction first (more accurate for vendor)
            amount = None
            vs = None
            vendor = None

            try:
                from parsers.llm_extractor import extract_invoice_data_llm
                llm_data = extract_invoice_data_llm(text)
                if llm_data.get("amount"):
                    amount = llm_data["amount"]
                if llm_data.get("vs"):
                    vs = llm_data["vs"]
                if llm_data.get("vendor"):
                    vendor = llm_data["vendor"]
            except Exception:
                pass

            # Fallback to regex if LLM didn't extract
            if amount is None:
                amount = extract_amount(text)
            if vs is None:
                vs = extract_vs(text)
            if vendor is None:
                vendor = extract_vendor(text)

            invoice_date_dt = extract_date(text)

            # If no amount found in text, try e-kasa as fallback
            if amount is None:
                ekasa_receipt = parse_ekasa_pdf(pdf_path)
                if ekasa_receipt:
                    return Invoice(
                        file_path=pdf_path,
                        invoice_date=ekasa_receipt.issue_date.date(),
                        invoice_number=ekasa_receipt.receipt_id,
                        payment_type="card",
                        vendor=ekasa_receipt.vendor_name,
                        amount=ekasa_receipt.total_price,
                        vs=None
                    )

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
        # Try e-kasa as last resort
        try:
            ekasa_receipt = parse_ekasa_pdf(pdf_path)
            if ekasa_receipt:
                return Invoice(
                    file_path=pdf_path,
                    invoice_date=ekasa_receipt.issue_date.date(),
                    invoice_number=ekasa_receipt.receipt_id,
                    payment_type="card",
                    vendor=ekasa_receipt.vendor_name,
                    amount=ekasa_receipt.total_price,
                    vs=None
                )
        except Exception:
            pass
        return None
