from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional


@dataclass
class Transaction:
    """Represents a bank transaction."""

    id: str
    date: date
    amount: Decimal
    currency: str
    counter_account: str
    counter_name: str
    vs: str  # Variable Symbol
    note: str
    transaction_type: str
    raw_type: str  # Original type from CSV

    @property
    def is_card(self) -> bool:
        """Check if this is a card transaction."""
        return self.transaction_type == "card"

    @property
    def is_wire(self) -> bool:
        """Check if this is a wire transfer."""
        return self.transaction_type == "wire"

    @property
    def is_fee(self) -> bool:
        """Check if this is a fee/tax transaction."""
        return self.transaction_type == "fee"

    @property
    def abs_amount(self) -> Decimal:
        """Get absolute value of amount."""
        return abs(self.amount)

    def __str__(self) -> str:
        return f"Transaction({self.date}, {self.amount} {self.currency}, {self.note[:30]}...)"
