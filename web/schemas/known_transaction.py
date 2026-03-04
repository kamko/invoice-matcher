"""Schemas for known transaction rules."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class KnownTransactionBase(BaseModel):
    """Base schema for known transaction rules."""

    rule_type: str = Field(..., pattern="^(exact|pattern|vendor|note)$")
    vendor_pattern: Optional[str] = None
    note_pattern: Optional[str] = None  # Regex pattern for note field
    amount: Optional[Decimal] = None
    amount_min: Optional[Decimal] = None
    amount_max: Optional[Decimal] = None
    vs_pattern: Optional[str] = None
    counter_account: Optional[str] = None
    reason: str = Field(..., min_length=1, max_length=500)
    category: Optional[str] = None
    is_active: bool = True


class KnownTransactionCreate(KnownTransactionBase):
    """Schema for creating a known transaction rule."""

    pass


class KnownTransactionUpdate(BaseModel):
    """Schema for updating a known transaction rule."""

    rule_type: Optional[str] = Field(None, pattern="^(exact|pattern|vendor|note)$")
    vendor_pattern: Optional[str] = None
    note_pattern: Optional[str] = None
    amount: Optional[Decimal] = None
    amount_min: Optional[Decimal] = None
    amount_max: Optional[Decimal] = None
    vs_pattern: Optional[str] = None
    counter_account: Optional[str] = None
    reason: Optional[str] = Field(None, min_length=1, max_length=500)
    category: Optional[str] = None
    is_active: Optional[bool] = None


class KnownTransactionResponse(KnownTransactionBase):
    """Schema for known transaction rule response."""

    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
