"""SQLAlchemy ORM models."""

from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, DateTime,
    ForeignKey, Text, JSON
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class KnownTransaction(Base):
    """Known transaction rules for automatic matching."""

    __tablename__ = "known_transactions"

    id = Column(Integer, primary_key=True, index=True)
    rule_type = Column(String(20), nullable=False)  # 'exact', 'pattern', 'vendor'
    vendor_pattern = Column(String(255), nullable=True)  # Regex pattern for vendor/counter_name
    note_pattern = Column(String(255), nullable=True)  # Regex pattern for note field
    amount = Column(Numeric(12, 2), nullable=True)  # Exact match
    amount_min = Column(Numeric(12, 2), nullable=True)  # Range match
    amount_max = Column(Numeric(12, 2), nullable=True)  # Range match
    vs_pattern = Column(String(50), nullable=True)  # Variable symbol pattern
    counter_account = Column(String(100), nullable=True)
    reason = Column(String(500), nullable=False)  # "Monthly loan payment"
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship to matches
    matches = relationship("KnownTransactionMatch", back_populates="rule")


class KnownTransactionMatch(Base):
    """Audit trail linking transactions to known transaction rules."""

    __tablename__ = "known_transaction_matches"

    id = Column(Integer, primary_key=True, index=True)
    rule_id = Column(Integer, ForeignKey("known_transactions.id"), nullable=False)
    transaction_id = Column(String(100), nullable=False)  # Bank transaction ID
    session_id = Column(Integer, ForeignKey("reconciliation_sessions.id"), nullable=True)
    matched_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    transaction_data = Column(JSON, nullable=True)  # Store transaction details

    # Relationships
    rule = relationship("KnownTransaction", back_populates="matches")
    session = relationship("ReconciliationSession", back_populates="known_matches")


class ReconciliationSession(Base):
    """Session state for reconciliation runs - kept for migration compatibility."""

    __tablename__ = "reconciliation_sessions"

    id = Column(Integer, primary_key=True, index=True)
    from_date = Column(DateTime, nullable=False)
    to_date = Column(DateTime, nullable=False)
    gdrive_folder_id = Column(String(255), nullable=True)
    status = Column(String(20), default="pending")  # pending, processing, completed, failed
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    # Results cache
    results_json = Column(JSON, nullable=True)
    matched_count = Column(Integer, default=0)
    unmatched_count = Column(Integer, default=0)
    review_count = Column(Integer, default=0)
    known_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)

    # Relationships
    known_matches = relationship("KnownTransactionMatch", back_populates="session")


class MonthlyReconciliation(Base):
    """Monthly reconciliation data - organized by year-month."""

    __tablename__ = "monthly_reconciliations"

    id = Column(Integer, primary_key=True, index=True)
    year_month = Column(String(7), unique=True, nullable=False, index=True)  # "2026-02"
    gdrive_folder_id = Column(String(255), nullable=True)
    fio_token_hash = Column(String(64), nullable=True)  # Store hash for validation
    status = Column(String(20), default="pending")  # pending, processing, completed, failed
    last_synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Results cache
    results_json = Column(JSON, nullable=True)
    matched_count = Column(Integer, default=0)
    unmatched_count = Column(Integer, default=0)
    review_count = Column(Integer, default=0)
    known_count = Column(Integer, default=0)
    fee_count = Column(Integer, default=0)
    income_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
