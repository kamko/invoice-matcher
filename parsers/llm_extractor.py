"""LLM-based invoice data extraction using OpenRouter."""

import base64
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, TypedDict, Union

from openai import OpenAI


class InvoiceData(TypedDict, total=False):
    """Extracted invoice data."""
    amount: Optional[Decimal]
    vs: Optional[str]
    vendor: Optional[str]
    iban: Optional[str]


class MultiInvoiceData(TypedDict, total=False):
    """Multiple invoices/receipts extracted from a single PDF."""
    invoices: List[InvoiceData]
    count: int


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
- amount_to_pay: The final amount the customer must pay (after any discounts, prepayments, etc). Just the number.
- variable_symbol: Payment reference / VS / Variabilný symbol. Digits only, remove any slashes or dashes.
- vendor_name: Name of the company issuing the invoice (the seller/supplier).
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
- amount: The total/final amount. Just the number.
- vendor: Name of the company/store.
- date: Date of the receipt/invoice (YYYY-MM-DD format if possible).

IMPORTANT: If you see multiple receipts (e.g., 2 separate receipts on different pages or same page), return ALL of them as separate objects in the array.

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

    prompt = f"""Extract ALL receipts/invoices from these images ({len(images_base64)} page(s)).

Return a JSON array. For EACH receipt found, extract:
- amount: The total amount. Just the number.
- vendor: Name of the company/store.

IMPORTANT: If multiple receipts exist, return ALL as separate objects.

Return ONLY valid JSON array: [{{"amount": 12.50, "vendor": "Store"}}]

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
