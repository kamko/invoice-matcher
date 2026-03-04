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

    def __str__(self) -> str:
        return f"Invoice({self.filename}, {self.amount}, {self.vendor})"
