"""LLM-based invoice data extraction using OpenRouter."""

import json
import os
import re
from decimal import Decimal
from pathlib import Path
from typing import Optional, TypedDict

from openai import OpenAI

# Load .env file if exists
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


class InvoiceData(TypedDict, total=False):
    """Extracted invoice data."""
    amount: Optional[Decimal]
    vs: Optional[str]
    vendor: Optional[str]
    iban: Optional[str]


# Cheap models on OpenRouter
# google/gemini-2.5-flash-lite      - cheap & fast
# openai/gpt-4o-mini                - $0.15/1M in
# anthropic/claude-3-haiku          - $0.25/1M in
DEFAULT_MODEL = "google/gemini-2.5-flash-lite"


def extract_invoice_data_llm(text: str, model: str = None) -> InvoiceData:
    """
    Extract invoice data using OpenRouter.

    Args:
        text: Full text extracted from invoice PDF
        model: OpenRouter model ID (or set OPENROUTER_MODEL env var)

    Returns:
        Dictionary with amount, vs, vendor, iban (all optional)
    """
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return {}

    # Model selection: param > env var > default
    model = model or os.environ.get("OPENROUTER_MODEL") or DEFAULT_MODEL

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
