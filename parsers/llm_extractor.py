"""LLM-based invoice data extraction using OpenRouter."""

import base64
import json
import re
from decimal import Decimal
from pathlib import Path
from datetime import date as DateType
from typing import List, Optional, TypedDict, Union

from openai import OpenAI


class InvoiceData(TypedDict, total=False):
    """Extracted invoice data."""
    amount: Optional[Decimal]
    date: Optional[DateType]
    vs: Optional[str]
    vendor: Optional[str]
    iban: Optional[str]


class MultiInvoiceData(TypedDict, total=False):
    """Multiple invoices/receipts extracted from a single PDF."""
    invoices: List[InvoiceData]
    count: int


def extract_vendor_from_note_llm(note: str, model: str = None) -> Optional[str]:
    """
    Extract vendor/company name from a bank transaction note using LLM.

    Args:
        note: Transaction note/description from bank statement
        model: OpenRouter model ID

    Returns:
        Normalized vendor name or None
    """
    api_key, default_model = _get_settings()
    if not api_key or not note:
        return None

    model = model or default_model

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    prompt = f"""Extract the company/vendor name from this bank transaction description.
Return ONLY the company name in lowercase, no other text. If unclear, return "unknown".

Transaction: {note[:500]}

Company name:"""

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=50,
            messages=[{"role": "user", "content": prompt}]
        )

        vendor = response.choices[0].message.content.strip().lower()
        # Clean up common artifacts
        vendor = vendor.replace('"', '').replace("'", "").strip()
        if vendor and vendor != "unknown" and len(vendor) < 100:
            return vendor
        return None

    except Exception:
        return None


# Cache for LLM vendor extractions (to avoid repeated API calls)
_vendor_cache: dict = {}

# Cache for vendor comparisons
_vendor_comparison_cache: dict = {}


def compare_vendors_llm(vendor1: str, vendor2: str, model: str = None) -> float:
    """
    Compare two vendor names using LLM to determine if they're the same company.

    Args:
        vendor1: First vendor name (e.g., from transaction)
        vendor2: Second vendor name (e.g., from invoice)
        model: OpenRouter model ID

    Returns:
        Score 0.0 to 1.0 (1.0 = definitely same company, 0.0 = definitely different)

    Raises:
        RuntimeError: If LLM API is unavailable (no API key, etc.)
    """
    api_key, default_model = _get_settings()
    if not api_key:
        raise RuntimeError("No OpenRouter API key configured")
    if not vendor1 or not vendor2:
        raise RuntimeError("Empty vendor name")

    # Normalize for cache key
    key = tuple(sorted([vendor1.lower().strip(), vendor2.lower().strip()]))
    if key in _vendor_comparison_cache:
        return _vendor_comparison_cache[key]

    model = model or default_model

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    prompt = f"""Are these two vendor/company names referring to the SAME company?

Vendor 1: {vendor1}
Vendor 2: {vendor2}

Answer with just one word: YES or NO"""

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}]
        )

        answer = response.choices[0].message.content.strip().upper()
        score = 1.0 if "YES" in answer else 0.0
        _vendor_comparison_cache[key] = score
        return score

    except Exception as e:
        raise RuntimeError(f"LLM API call failed: {e}")


def get_vendor_from_note_cached(note: str) -> Optional[str]:
    """Get vendor from note, using cache to avoid repeated LLM calls."""
    if not note:
        return None

    # Use first 100 chars as cache key
    cache_key = note[:100]
    if cache_key in _vendor_cache:
        return _vendor_cache[cache_key]

    vendor = extract_vendor_from_note_llm(note)
    _vendor_cache[cache_key] = vendor
    return vendor


def _get_settings():
    """Get OpenRouter settings from web config."""
    try:
        from web.config import settings
        return settings.openrouter_api_key, settings.openrouter_model
    except ImportError:
        # Fallback for CLI usage without web module
        import os
        return (
            os.environ.get("OPENROUTER_API_KEY", ""),
            os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash-lite")
        )


def extract_invoice_data_llm(text: str, model: str = None) -> InvoiceData:
    """
    Extract invoice data using OpenRouter.

    Args:
        text: Full text extracted from invoice PDF
        model: OpenRouter model ID

    Returns:
        Dictionary with amount, vs, vendor, iban (all optional)
    """
    api_key, default_model = _get_settings()
    if not api_key:
        return {}

    model = model or default_model

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    prompt = """Extract the following from this invoice. Return ONLY valid JSON, no other text.

Fields to extract:
- amount_to_pay: The TOTAL amount INCLUDING VAT/DPH (the gross total, not the net/base amount). Look for "Celkom vrátane DPH", "Total with VAT", "Suma s DPH", "Celková suma", "Grand Total". If you see both with-VAT and without-VAT amounts, ALWAYS use the WITH-VAT amount. Just the number.
- invoice_date: The date of taxable supply (NOT issue date) in YYYY-MM-DD format. Look for "Dátum zdaniteľného plnenia", "Datum zdanitelneho plnenia", "Tax point date", "Date of supply". If not found, use the invoice issue date ("Dátum vystavenia", "Date of issue").
- variable_symbol: Payment reference / VS / Variabilný symbol. Digits only, remove any slashes or dashes.
- vendor_name: Name of the company issuing the invoice (the seller/supplier/Dodávateľ). This is NOT the bank - ignore any bank names in "Bankové spojenie" or payment details section. Look for "Dodávateľ", "Supplier", "From", "Seller".
- iban: Bank account IBAN for payment.

If a field cannot be found, use null.

Invoice text:
```
{text}
```

JSON response:"""

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=256,
            messages=[
                {"role": "user", "content": prompt.format(text=text[:8000])}
            ]
        )

        content = response.choices[0].message.content.strip()

        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group()

        data = json.loads(content)

        result: InvoiceData = {}

        # Parse amount
        if data.get("amount_to_pay"):
            try:
                amt_str = str(data["amount_to_pay"]).replace(",", ".").replace(" ", "")
                result["amount"] = Decimal(amt_str)
            except:
                pass

        # Parse date
        if data.get("invoice_date"):
            try:
                from datetime import datetime
                date_str = str(data["invoice_date"]).strip()
                # Try YYYY-MM-DD format
                parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                result["date"] = parsed_date
            except:
                pass

        # Parse VS (digits only)
        if data.get("variable_symbol"):
            vs = re.sub(r"[^\d]", "", str(data["variable_symbol"]))
            if vs:
                result["vs"] = vs

        # Vendor
        if data.get("vendor_name"):
            result["vendor"] = str(data["vendor_name"]).strip()

        # IBAN
        if data.get("iban"):
            iban = str(data["iban"]).replace(" ", "").upper()
            if iban:
                result["iban"] = iban

        return result

    except Exception as e:
        print(f"LLM extraction failed: {e}")
        return {}


def extract_invoice_data_from_image(pdf_path: Path, model: str = None) -> InvoiceData:
    """
    Extract invoice data from a scanned PDF using vision LLM.

    Args:
        pdf_path: Path to the PDF file
        model: OpenRouter model ID (must support vision)

    Returns:
        Dictionary with amount, vs, vendor, iban (all optional)
    """
    api_key, default_model = _get_settings()
    if not api_key:
        return {}

    model = model or default_model

    try:
        import fitz  # pymupdf

        # Convert all pages to images (max 5 pages to limit costs)
        doc = fitz.open(pdf_path)
        images_base64 = []
        max_pages = min(len(doc), 5)

        for i in range(max_pages):
            page = doc[i]
            # Render at 150 DPI for good quality without being too large
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            img_base64 = base64.b64encode(img_bytes).decode("utf-8")
            images_base64.append(img_base64)

        doc.close()

        if not images_base64:
            return {}

    except Exception as e:
        print(f"Failed to convert PDF to image: {e}")
        return {}

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    prompt = f"""Extract ALL receipts/invoices from these images ({len(images_base64)} page(s)). A single PDF may contain MULTIPLE receipts.

Return a JSON array of receipts. For EACH receipt found, extract:
- amount: The TOTAL amount INCLUDING VAT/tax (the gross total, NOT the net/base amount). Look for "Celkom vrátane DPH", "Total with VAT", "Grand Total". Just the number.
- vendor: Name of the company/store.
- date: Date of the receipt/invoice (YYYY-MM-DD format if possible).

IMPORTANT: If you see multiple receipts (e.g., 2 separate receipts on different pages or same page), return ALL of them as separate objects in the array.
IMPORTANT: Always use WITH-VAT amounts, not without-VAT amounts.

Return ONLY valid JSON array, no other text. Example format:
[{{"amount": 12.50, "vendor": "Store Name", "date": "2025-01-15"}}]

If only one receipt, still return as array with one element.
If no receipts found, return empty array: []

JSON response:"""

    # Build content with all images
    content = [{"type": "text", "text": prompt}]
    for img_b64 in images_base64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{img_b64}"}
        })

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": content
                }
            ]
        )

        response_content = response.choices[0].message.content.strip()

        # Extract JSON array from response
        # Try to find array first
        array_match = re.search(r'\[[\s\S]*\]', response_content)
        if array_match:
            response_content = array_match.group()
        else:
            # Fallback: try single object and wrap in array
            json_match = re.search(r'\{[^{}]*\}', response_content, re.DOTALL)
            if json_match:
                response_content = f"[{json_match.group()}]"
            else:
                return {}

        data_list = json.loads(response_content)

        if not isinstance(data_list, list):
            data_list = [data_list]

        # Return the first receipt for backward compatibility
        # But store all receipts info
        if not data_list:
            return {}

        # For now, return first receipt (most common case)
        # TODO: Handle multiple receipts in caller
        data = data_list[0]
        result: InvoiceData = {}

        if data.get("amount"):
            try:
                amt_str = str(data["amount"]).replace(",", ".").replace(" ", "")
                result["amount"] = Decimal(amt_str)
            except:
                pass

        if data.get("vendor"):
            result["vendor"] = str(data["vendor"]).strip()

        # Store count of receipts found for caller to know
        if len(data_list) > 1:
            print(f"LLM found {len(data_list)} receipts in PDF - only using first one for now")

        return result

    except Exception as e:
        print(f"LLM vision extraction failed: {e}")
        return {}


# Cache for match scoring
_match_score_cache: dict = {}


def select_best_invoice_llm(
    trans_date: str,
    trans_amount: str,
    trans_note: str,
    trans_counter_name: str,
    trans_vs: str,
    trans_type: str,
    candidates: list[dict],  # List of {filename, date, amount, vendor, type, vs}
    model: str = None
) -> tuple[int, float]:
    """
    Ask LLM to select the best matching invoice from candidates.

    Returns:
        Tuple of (index of best match, confidence score 0-1)
        Returns (-1, 0.0) if no good match
    """
    api_key, default_model = _get_settings()
    if not api_key or not candidates:
        return -1, 0.0

    model = model or default_model

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    # Build candidate list
    candidate_text = ""
    for i, c in enumerate(candidates):
        candidate_text += f"\n{i+1}. {c['filename']} - {c['amount']} EUR, {c['date']}, vendor: {c['vendor']}"

    prompt = f"""Which invoice was paid by this transaction? Choose the BEST match.

TRANSACTION:
- Date: {trans_date}
- Amount: {trans_amount} EUR
- Type: {trans_type}
- Note: {trans_note or '(empty)'}
- Counter name: {trans_counter_name or '(empty)'}
- VS: {trans_vs or '(none)'}

CANDIDATE INVOICES:{candidate_text}

RULES:
- Invoice filename format: YYYY-MM-DD-NNN_type_vendor.pdf
- Transaction note often contains vendor name after "Nákup:" for card payments
- Amount match (ignoring sign) is crucial
- If none match well, answer 0

Answer format: NUMBER CONFIDENCE
Example: "2 85" means invoice #2 with 85% confidence
Example: "0 0" means no match

Your answer:"""

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=20,
            messages=[{"role": "user", "content": prompt}]
        )

        answer = response.choices[0].message.content.strip()

        # Extract all numbers from response (handles "2 85" or "The answer is 2 with 85%")
        numbers = re.findall(r'\d+', answer)
        if len(numbers) >= 2:
            idx = int(numbers[0])
            conf = int(numbers[1]) / 100.0
            if idx > 0 and idx <= len(candidates):
                return idx - 1, min(1.0, max(0.0, conf))
        elif len(numbers) == 1:
            idx = int(numbers[0])
            if idx > 0 and idx <= len(candidates):
                return idx - 1, 0.7  # Default confidence
        return -1, 0.0

    except Exception as e:
        print(f"LLM selection failed: {e}")
        return -1, 0.0


def get_vendor_aliases() -> list:
    """Get all vendor aliases from the database for LLM context."""
    try:
        from web.database import SessionLocal
        from web.database.models import VendorAlias

        db = SessionLocal()
        aliases = db.query(VendorAlias).order_by(
            VendorAlias.confidence_count.desc()
        ).limit(50).all()

        result = []
        for a in aliases:
            result.append(f"{a.transaction_vendor} = {a.invoice_vendor}")

        db.close()
        return result
    except Exception:
        return []


def score_transaction_invoice_match(
    trans_date: str,
    trans_amount: str,
    trans_note: str,
    trans_counter_name: str,
    trans_counter_account: str,
    trans_vs: str,
    trans_type: str,
    inv_filename: str,
    inv_date: str,
    inv_amount: str,
    inv_vendor: str,
    inv_vs: str,
    inv_type: str,
    model: str = None
) -> float:
    """
    Use LLM to score how likely a transaction matches an invoice.

    Returns:
        Score 0.0 to 1.0 (1.0 = definite match, 0.0 = no match)
    """
    api_key, default_model = _get_settings()
    if not api_key:
        return 0.0

    # Cache key based on transaction ID + invoice filename
    cache_key = f"{trans_date}|{trans_amount}|{inv_filename}"
    if cache_key in _match_score_cache:
        return _match_score_cache[cache_key]

    model = model or default_model

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    # Get learned vendor aliases
    aliases = get_vendor_aliases()
    aliases_text = ""
    if aliases:
        aliases_text = "\n\nKNOWN VENDOR ALIASES (same company, different names):\n" + "\n".join(f"- {a}" for a in aliases[:20])

    prompt = f"""Match this bank transaction to this invoice. Give confidence score 0-100.

TRANSACTION:
- Date: {trans_date}
- Amount: {trans_amount} EUR
- Type: {trans_type}
- Note: {trans_note or '(empty)'}
- Counter name: {trans_counter_name or '(empty)'}
- Counter IBAN: {trans_counter_account or '(empty)'}
- VS: {trans_vs or '(none)'}

INVOICE:
- Filename: {inv_filename}
- Date: {inv_date}
- Amount: {inv_amount} EUR
- Vendor: {inv_vendor}
- Type: {inv_type}
- VS: {inv_vs or '(none)'}
{aliases_text}

MATCHING RULES:
- Amounts matching (ignoring sign) is the STRONGEST indicator - transaction is negative (expense), invoice is positive
- Same or nearby date (within a few days) is a strong signal
- If vendors appear in KNOWN VENDOR ALIASES list above, they are DEFINITELY the same company (100% match on vendor)
- Related companies are the SAME vendor: Alza.cz = Alza SK, Orlen CZ = Orlen SK, etc.
- Vendor name in filename may be abbreviated/slugified - match the actual company, not exact text
- For wire transfers, counter name often shows intermediary bank, NOT the actual vendor
- Card transactions: vendor is usually in the Note field ("Nakup: Company Name...")

Score 0-100 (just the number):"""

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}]
        )

        answer = response.choices[0].message.content.strip()
        # Extract number from response
        match = re.search(r'\d+', answer)
        if match:
            score = int(match.group()) / 100.0
            score = max(0.0, min(1.0, score))  # Clamp to 0-1
            _match_score_cache[cache_key] = score
            return score
        return 0.0

    except Exception as e:
        print(f"LLM match scoring failed: {e}")
        return 0.0


def extract_all_receipts_from_image(pdf_path: Path, model: str = None) -> List[InvoiceData]:
    """
    Extract ALL receipts/invoices from a scanned PDF using vision LLM.

    Args:
        pdf_path: Path to the PDF file
        model: OpenRouter model ID (must support vision)

    Returns:
        List of dictionaries with amount, vendor for each receipt found
    """
    api_key, default_model = _get_settings()
    if not api_key:
        return []

    model = model or default_model

    try:
        import fitz  # pymupdf

        doc = fitz.open(pdf_path)
        images_base64 = []
        max_pages = min(len(doc), 5)

        for i in range(max_pages):
            page = doc[i]
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            img_base64 = base64.b64encode(img_bytes).decode("utf-8")
            images_base64.append(img_base64)

        doc.close()

        if not images_base64:
            return []

    except Exception as e:
        print(f"Failed to convert PDF to image: {e}")
        return []

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    prompt = f"""Extract ONLY actual invoices from these images ({len(images_base64)} page(s)).

Return a JSON array. For EACH INVOICE found, extract:
- amount: The TOTAL amount INCLUDING VAT/tax (gross total). Look for "Celkom vrátane DPH", "Total with VAT". Just the number.
- vendor: Name of the company/store issuing the invoice.

CRITICAL RULES:
- Only extract ACTUAL INVOICES with invoice numbers, dates, and totals
- IGNORE summary pages, monthly statements, account overviews, delivery notes
- IGNORE pages that just list multiple transactions or totals without being a proper invoice
- If a PDF has 1 invoice + 2 summary pages, return ONLY the 1 invoice
- Each invoice should have a clear total amount payable

Return ONLY valid JSON array: [{{"amount": 12.50, "vendor": "Store"}}]
Return empty array [] if no actual invoices found.

JSON response:"""

    content = [{"type": "text", "text": prompt}]
    for img_b64 in images_base64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{img_b64}"}
        })

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=512,
            messages=[{"role": "user", "content": content}]
        )

        response_content = response.choices[0].message.content.strip()

        array_match = re.search(r'\[[\s\S]*\]', response_content)
        if array_match:
            response_content = array_match.group()
        else:
            json_match = re.search(r'\{[^{}]*\}', response_content, re.DOTALL)
            if json_match:
                response_content = f"[{json_match.group()}]"
            else:
                return []

        data_list = json.loads(response_content)

        if not isinstance(data_list, list):
            data_list = [data_list]

        results: List[InvoiceData] = []
        for data in data_list:
            result: InvoiceData = {}
            if data.get("amount"):
                try:
                    amt_str = str(data["amount"]).replace(",", ".").replace(" ", "")
                    result["amount"] = Decimal(amt_str)
                except:
                    pass
            if data.get("vendor"):
                result["vendor"] = str(data["vendor"]).strip()
            if result:
                results.append(result)

        return results

    except Exception as e:
        print(f"LLM multi-receipt extraction failed: {e}")
        return []
