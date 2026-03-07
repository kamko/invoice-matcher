"""Schemas for reconciliation endpoints."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ReconcileRequest(BaseModel):
    """Request to run reconciliation."""

    from_date: date
    to_date: date
    fio_token: str = Field(..., min_length=1)
    gdrive_folder_id: Optional[str] = None
    invoice_dir: Optional[str] = None  # Alternative to gdrive


class TransactionResponse(BaseModel):
    """Response schema for a transaction."""

    id: str
    date: date
    amount: Decimal
    currency: str
    counter_account: Optional[str] = None
    counter_name: Optional[str] = None
    vs: Optional[str] = None
    note: Optional[str] = None
    transaction_type: str
    rule_reason: Optional[str] = None  # For known transactions


class MatchResultResponse(BaseModel):
    """Response schema for a match result."""

    transaction: Optional[TransactionResponse] = None  # None for cash invoices
    invoice: Optional[Dict[str, Any]] = None
    confidence: float
    confidence_pct: int
    status: str
    strategy_scores: Dict[str, float]


class ReconcileResponse(BaseModel):
    """Response after starting reconciliation."""

    session_id: int
    status: str
    message: str


class SessionResponse(BaseModel):
    """Response with session details and results."""

    id: int
    from_date: datetime
    to_date: datetime
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None

    matched_count: int
    unmatched_count: int
    review_count: int
    known_count: int
    fee_count: int = 0
    income_count: int = 0

    matched: List[MatchResultResponse] = []
    unmatched: List[TransactionResponse] = []
    known: List[TransactionResponse] = []
    fees: List[TransactionResponse] = []
    income: List[TransactionResponse] = []
    unmatched_invoices: List[Dict[str, Any]] = []

    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class MonthlyReconcileRequest(BaseModel):
    """Request to run reconciliation for a specific month."""

    year_month: str = Field(..., pattern=r"^\d{4}-\d{2}$")  # "2026-02"
    fio_token: str = Field(..., min_length=1)
    gdrive_folder_id: Optional[str] = None
    invoice_dir: Optional[str] = None
    # Previous month folder for matching late payments
    prev_month_gdrive_folder_id: Optional[str] = None
    prev_month_invoice_dir: Optional[str] = None


class MonthResponse(BaseModel):
    """Response with monthly reconciliation data."""

    year_month: str
    status: str
    last_synced_at: Optional[datetime] = None
    created_at: datetime

    matched_count: Optional[int] = 0
    unmatched_count: Optional[int] = 0
    review_count: Optional[int] = 0
    known_count: Optional[int] = 0
    fee_count: Optional[int] = 0
    income_count: Optional[int] = 0
    skipped_count: Optional[int] = 0

    matched: List[MatchResultResponse] = []
    unmatched: List[TransactionResponse] = []
    known: List[TransactionResponse] = []
    fees: List[TransactionResponse] = []
    income: List[TransactionResponse] = []
    skipped: List[TransactionResponse] = []
    unmatched_invoices: List[Dict[str, Any]] = []

    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class MonthListItem(BaseModel):
    """Brief info for month listing."""

    year_month: str
    status: str
    matched_count: Optional[int] = 0
    unmatched_count: Optional[int] = 0
    review_count: Optional[int] = 0
    known_count: Optional[int] = 0
    fee_count: Optional[int] = 0
    income_count: Optional[int] = 0
    last_synced_at: Optional[datetime] = None
    gdrive_folder_id: Optional[str] = None
    gdrive_folder_name: Optional[str] = None


class SetFolderRequest(BaseModel):
    """Request to set Google Drive folder for a month."""

    folder_id: str
    folder_name: str


class MarkKnownRequest(BaseModel):
    """Request to mark a transaction as known."""

    transaction_id: str
    rule_type: str = Field(..., pattern="^(exact|pattern|vendor|note|account)$")
    reason: str = Field(..., min_length=1, max_length=500)
    vendor_pattern: Optional[str] = None
    note_pattern: Optional[str] = None  # Regex pattern for note field
    amount: Optional[Decimal] = None
    amount_min: Optional[Decimal] = None
    amount_max: Optional[Decimal] = None
    counter_account: Optional[str] = None


class MatchWithPdfResponse(BaseModel):
    """Response after matching with uploaded PDF."""

    success: bool
    message: str
    gdrive_file_id: Optional[str] = None
    invoice: Optional[Dict[str, Any]] = None
    warning: Optional[str] = None  # Set when force=true was used with amount mismatch
