"""Schemas for invoice endpoints."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field


class InvoiceBase(BaseModel):
    """Base invoice schema."""
    filename: str
    vendor: Optional[str] = None
    amount: Optional[Decimal] = None
    invoice_date: Optional[date] = None
    payment_type: Optional[str] = None  # wire/card/cash
    vs: Optional[str] = None
    iban: Optional[str] = None
    is_credit_note: bool = False


class InvoiceCreate(InvoiceBase):
    """Schema for creating an invoice."""
    gdrive_file_id: Optional[str] = None
    receipt_index: int = 0


class InvoiceUpdate(BaseModel):
    """Schema for updating an invoice."""
    vendor: Optional[str] = None
    amount: Optional[Decimal] = None
    invoice_date: Optional[date] = None
    payment_type: Optional[str] = None
    vs: Optional[str] = None
    iban: Optional[str] = None
    is_credit_note: Optional[bool] = None
    status: Optional[str] = None


class InvoiceResponse(InvoiceBase):
    """Response schema for an invoice."""
    id: int
    gdrive_file_id: Optional[str] = None
    receipt_index: int = 0
    status: str
    transaction_id: Optional[str] = None
    created_at: datetime

    # Computed field for month filter
    invoice_month: Optional[str] = None

    class Config:
        from_attributes = True


class InvoiceWithMatch(InvoiceResponse):
    """Invoice with matched transaction info."""
    matched_transaction: Optional['TransactionBrief'] = None


class TransactionBrief(BaseModel):
    """Brief transaction info for embedding in invoice."""
    id: str
    date: date
    amount: Decimal
    counter_name: Optional[str] = None

    class Config:
        from_attributes = True


class InvoiceListResponse(BaseModel):
    """Response for listing invoices."""
    invoices: List[InvoiceResponse]
    total: int
    unmatched: int
    matched: int


class MatchSuggestion(BaseModel):
    """A suggested match for an invoice."""
    transaction_id: str
    date: date
    amount: Decimal
    counter_name: Optional[str] = None
    vs: Optional[str] = None
    note: Optional[str] = None
    score: int  # 0-100


class InvoiceSuggestionsResponse(BaseModel):
    """Response with match suggestions for an invoice."""
    invoice_id: int
    suggestions: List[MatchSuggestion]


class MatchRequest(BaseModel):
    """Request to match an invoice to a transaction."""
    transaction_id: str


class ImportGDriveRequest(BaseModel):
    """Request to import invoices from GDrive folder."""
    folder_id: str
    year_month: Optional[str] = None  # Optional filter by month name pattern
