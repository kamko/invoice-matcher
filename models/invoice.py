from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Optional


@dataclass
class Invoice:
    """Represents an invoice extracted from PDF."""

    file_path: Path
    invoice_date: date
    invoice_number: str
    payment_type: str  # 'card' or 'wire'
    vendor: str
    amount: Optional[Decimal] = None
    vs: Optional[str] = None  # Variable Symbol extracted from PDF
    gdrive_file_id: Optional[str] = None  # Google Drive file ID

    @property
    def filename(self) -> str:
        """Get just the filename."""
        return self.file_path.name

    @property
    def is_card(self) -> bool:
        """Check if this is a card payment invoice."""
        return self.payment_type == "card"

    @property
    def is_wire(self) -> bool:
        """Check if this is a wire transfer invoice."""
        return self.payment_type == "wire"

    @property
    def is_credit_note(self) -> bool:
        """Check if this is a credit note (reversal of invoice).

        Credit notes represent refunds/credits coming back to the company.
        They should match with positive (income) transactions, not expenses.
        """
        filename_lower = self.filename.lower()
        return "credit-note" in filename_lower or "credit_note" in filename_lower

    @property
    def is_cash(self) -> bool:
        """Check if this is a cash payment invoice.

        Cash invoices are already paid (with cash) and don't need
        to match with any bank transaction.
        """
        return "_cash_" in self.filename.lower()

    def __str__(self) -> str:
        return f"Invoice({self.filename}, {self.amount}, {self.vendor})"
