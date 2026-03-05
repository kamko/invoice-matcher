"""Fio Bank API client for fetching transactions directly."""

import os
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from fiobank import FioBank, ThrottlingError

from models.transaction import Transaction


def fetch_transactions_from_api(
    token: str,
    from_date: date,
    to_date: date,
) -> List[Transaction]:
    """
    Fetch transactions directly from Fio Bank API.

    Args:
        token: Fio Bank API token (from internet banking settings)
        from_date: Start date for transaction period
        to_date: End date for transaction period

    Returns:
        List of Transaction objects
    """
    client = FioBank(token, decimal=True)

    try:
        info, trans_generator = client.transactions(from_date, to_date)
    except ThrottlingError:
        raise RuntimeError(
            "Fio API rate limit: token can only be used once per 30 seconds. "
            "Please wait and try again."
        )

    transactions = []

    for trans in trans_generator:
        transaction = _convert_api_transaction(trans)
        if transaction:
            transactions.append(transaction)

    return transactions


def _convert_api_transaction(trans: dict) -> Optional[Transaction]:
    """Convert Fio API transaction dict to Transaction model."""
    # Get transaction date
    trans_date = trans.get("date")
    if not trans_date:
        return None

    if isinstance(trans_date, datetime):
        trans_date = trans_date.date()

    # Get amount
    amount = trans.get("amount")
    if amount is None:
        return None

    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))

    # Determine transaction type
    trans_type_raw = trans.get("type", "")
    transaction_type = _classify_type(trans_type_raw)

    # Build note from available fields
    note_parts = []
    if trans.get("recipient_message"):
        note_parts.append(trans["recipient_message"])
    if trans.get("comment"):
        note_parts.append(trans["comment"])
    if trans.get("user_identification"):
        note_parts.append(trans["user_identification"])
    note = " | ".join(note_parts) if note_parts else ""

    return Transaction(
        id=str(trans.get("transaction_id", "")),
        date=trans_date,
        amount=amount,
        currency=trans.get("currency", "EUR"),
        counter_account=trans.get("account_number_full", ""),
        counter_name=trans.get("account_name", ""),
        vs=trans.get("variable_symbol", "") or "",
        note=note,
        transaction_type=transaction_type,
        raw_type=trans_type_raw,
    )


def _classify_type(raw_type: str) -> str:
    """Classify transaction type from API type field."""
    raw_type_lower = raw_type.lower()

    # Fee transactions
    if "daň" in raw_type_lower or "poplatek" in raw_type_lower:
        return "fee"

    # Card transactions
    if "kartou" in raw_type_lower or "card" in raw_type_lower:
        return "card"

    # Wire transfers (including SEPA direct debit)
    if any(term in raw_type_lower for term in [
        "platba", "prevod", "příjem", "europlatba", "bezhotovostní",
        "sepa", "inkaso"
    ]):
        return "wire"

    return "other"


def get_token_from_env() -> Optional[str]:
    """Get Fio API token from environment variable."""
    return os.environ.get("FIO_API_TOKEN")
