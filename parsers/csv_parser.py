"""Parser for Fio Bank CSV statements."""

import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List

import pandas as pd

from models.transaction import Transaction


def parse_bank_statement(csv_path: Path) -> List[Transaction]:
    """
    Parse a Fio Bank CSV statement file.

    Args:
        csv_path: Path to the CSV file

    Returns:
        List of Transaction objects
    """
    # Read CSV, skipping first 9 metadata rows
    df = pd.read_csv(
        csv_path,
        sep=";",
        skiprows=9,
        encoding="utf-8",
        dtype=str,
        keep_default_na=False
    )

    transactions = []

    for _, row in df.iterrows():
        # Skip empty rows
        if not row.get("ID operácie", "").strip():
            continue

        # Parse date (DD.MM.YYYY format)
        date_str = row.get("Dátum", "")
        try:
            trans_date = datetime.strptime(date_str, "%d.%m.%Y").date()
        except ValueError:
            continue

        # Parse amount
        amount_str = row.get("Objem", "0").replace(",", ".")
        try:
            amount = Decimal(amount_str)
        except:
            continue

        # Get transaction type
        raw_type = row.get("Typ", "")
        transaction_type = classify_transaction_type(raw_type)

        # Extract note/vendor info
        note = row.get("Poznámka", "") or ""
        if not note:
            # Try alternative columns
            note = row.get("Správa pre príjemcu", "") or row.get("Názov protiúčtu", "") or ""

        transaction = Transaction(
            id=row.get("ID operácie", ""),
            date=trans_date,
            amount=amount,
            currency=row.get("Mena", "EUR"),
            counter_account=row.get("Protiúčet", ""),
            counter_name=row.get("Názov protiúčtu", ""),
            vs=row.get("VS", ""),
            note=note,
            transaction_type=transaction_type,
            raw_type=raw_type
        )

        transactions.append(transaction)

    return transactions


def classify_transaction_type(raw_type: str) -> str:
    """
    Classify the transaction type into card, wire, or fee.

    Args:
        raw_type: Raw type string from CSV

    Returns:
        'card', 'wire', or 'fee'
    """
    raw_type_lower = raw_type.lower()

    # Fee transactions
    if "daň" in raw_type_lower or "poplatok" in raw_type_lower:
        return "fee"

    # Card transactions
    if "kartou" in raw_type_lower:
        return "card"

    # Wire transfers (various types)
    if any(term in raw_type_lower for term in [
        "europlatba", "platba", "prevod", "príjem", "bezhotovostný"
    ]):
        return "wire"

    return "other"


def extract_vendor_from_note(note: str) -> str:
    """
    Extract vendor name from transaction note.

    Args:
        note: Transaction note/description

    Returns:
        Extracted vendor name
    """
    # Pattern for card transactions: "Nákup: VENDOR NAME, CITY, COUNTRY, dne ..."
    match = re.search(r"Nákup:\s*([^,]+)", note)
    if match:
        return match.group(1).strip()

    return note[:50] if note else ""
