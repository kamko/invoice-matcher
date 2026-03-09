"""Schemas for transaction endpoints."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field


class TransactionBase(BaseModel):
    """Base transaction schema."""
    id: str
    date: date
    amount: Decimal
    currency: str = 'CZK'
    counter_account: Optional[str] = None
    counter_name: Optional[str] = None
    vs: Optional[str] = None
    note: Optional[str] = None
    type: Optional[str] = None  # expense/income/fee
    raw_type: Optional[str] = None


class TransactionResponse(TransactionBase):
    """Response schema for a transaction."""
    status: str  # unmatched/matched/known/skipped
    known_rule_id: Optional[int] = None
    skip_reason: Optional[str] = None
    extracted_vendor: Optional[str] = None  # LLM-extracted clean vendor name
    fetched_at: Optional[datetime] = None

    # Rule info if known
    rule_reason: Optional[str] = None

    class Config:
        from_attributes = True


class TransactionWithMatch(TransactionResponse):
    """Transaction with matched invoice info."""
    matched_invoice: Optional['InvoiceBrief'] = None


class InvoiceBrief(BaseModel):
    """Brief invoice info for embedding in transaction."""
    id: int
    filename: str
    vendor: Optional[str] = None
    amount: Optional[Decimal] = None
    invoice_date: Optional[date] = None

    class Config:
        from_attributes = True


class TransactionListResponse(BaseModel):
    """Response for listing transactions."""
    transactions: List[TransactionResponse]
    total: int
    unmatched: int
    matched: int
    known: int
    skipped: int


class InvoiceSuggestion(BaseModel):
    """A suggested invoice match for a transaction."""
    invoice_id: int
    filename: str
    vendor: Optional[str] = None
    amount: Optional[Decimal] = None
    invoice_date: Optional[date] = None
    score: int  # 0-100


class TransactionSuggestionsResponse(BaseModel):
    """Response with invoice suggestions for a transaction."""
    transaction_id: str
    suggestions: List[InvoiceSuggestion]


class FetchTransactionsRequest(BaseModel):
    """Request to fetch transactions from Fio Bank."""
    fio_token: str = Field(..., min_length=1)
    from_date: date
    to_date: date


class FetchTransactionsResponse(BaseModel):
    """Response after fetching transactions."""
    fetched: int
    new: int
    existing: int
    known_matched: int


class SkipTransactionRequest(BaseModel):
    """Request to skip a transaction."""
    reason: str = Field(default='', max_length=255)


class MarkKnownRequest(BaseModel):
    """Request to create a known transaction rule."""
    rule_type: str = Field(..., pattern="^(exact|pattern|vendor|note|account)$")
    reason: str = Field(..., min_length=1, max_length=500)
    vendor_pattern: Optional[str] = None
    note_pattern: Optional[str] = None
    amount: Optional[Decimal] = None
    amount_min: Optional[Decimal] = None
    amount_max: Optional[Decimal] = None
    counter_account: Optional[str] = None


class UpdateTransactionRequest(BaseModel):
    """Request to update a transaction."""
    counter_name: Optional[str] = None
    note: Optional[str] = None
    vs: Optional[str] = None
    type: Optional[str] = None  # expense/income/fee
