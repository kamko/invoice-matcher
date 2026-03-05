"""LLM-based invoice data extraction using OpenRouter."""

import base64
import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Optional, TypedDict, Union

from openai import OpenAI


class InvoiceData(TypedDict, total=False):
    """Extracted invoice data."""
    amount: Optional[Decimal]
    vs: Optional[str]
    vendor: Optional[str]
    iban: Optional[str]


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

        # Convert first page to image
        doc = fitz.open(pdf_path)
        page = doc[0]
        # Render at 150 DPI for good quality without being too large
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        doc.close()

        # Encode as base64
        img_base64 = base64.b64encode(img_bytes).decode("utf-8")

    except Exception as e:
        print(f"Failed to convert PDF to image: {e}")
        return {}

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    prompt = """Extract the following from this invoice image. Return ONLY valid JSON, no other text.

Fields to extract:
- amount_to_pay: The final amount the customer must pay. Just the number.
- variable_symbol: Payment reference / VS / Variabilný symbol. Digits only.
- vendor_name: Name of the company issuing the invoice (the seller/supplier).
- iban: Bank account IBAN for payment.

If a field cannot be found, use null.

JSON response:"""

    try:
        response = client.chat.completions.create(
            model=model,
            max_tokens=256,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{img_base64}"
                            }
                        }
                    ]
                }
            ]
        )

        content = response.choices[0].message.content.strip()

        # Extract JSON from response
        json_match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
        if json_match:
            content = json_match.group()

        data = json.loads(content)

        result: InvoiceData = {}

        if data.get("amount_to_pay"):
            try:
                amt_str = str(data["amount_to_pay"]).replace(",", ".").replace(" ", "")
                result["amount"] = Decimal(amt_str)
            except:
                pass

        if data.get("variable_symbol"):
            vs = re.sub(r"[^\d]", "", str(data["variable_symbol"]))
            if vs:
                result["vs"] = vs

        if data.get("vendor_name"):
            result["vendor"] = str(data["vendor_name"]).strip()

        if data.get("iban"):
            iban = str(data["iban"]).replace(" ", "").upper()
            if iban:
                result["iban"] = iban

        return result

    except Exception as e:
        print(f"LLM vision extraction failed: {e}")
        return {}
