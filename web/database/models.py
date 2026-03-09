"""SQLAlchemy ORM models - simplified flat data model."""

from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, DateTime,
    ForeignKey, Text, JSON, LargeBinary, Date, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class AppSettings(Base):
    """Application settings stored in database."""

    __tablename__ = "app_settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Invoice(Base):
    """Invoices uploaded from GDrive or manually."""

    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    gdrive_file_id = Column(String(255), nullable=True, index=True)  # NULL for manual uploads
    receipt_index = Column(Integer, default=0)  # For multi-receipt PDFs
    filename = Column(String(255), nullable=False)
    vendor = Column(String(255), nullable=True)
    amount = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(3), default='EUR')  # EUR, USD, CZK, etc.
    invoice_date = Column(Date, nullable=True)  # Determines "invoice month" for VAT
    payment_type = Column(String(20), nullable=True)  # wire/card/cash
    vs = Column(String(50), nullable=True)  # Variable symbol (for wire)
    iban = Column(String(50), nullable=True)  # IBAN (for wire)
    is_credit_note = Column(Boolean, default=False)
    status = Column(String(20), default='unmatched')  # unmatched/matched/cash/exported
    transaction_id = Column(String(100), nullable=True, index=True)  # FK to matched transaction
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('gdrive_file_id', 'receipt_index', name='uq_invoice_gdrive_receipt'),
        UniqueConstraint('transaction_id', name='uq_invoice_transaction'),  # 1:1 enforcement
    )


class Transaction(Base):
    """Transactions fetched from Fio Bank."""

    __tablename__ = "transactions"

    id = Column(String(100), primary_key=True)  # Fio transaction ID
    date = Column(Date, nullable=False, index=True)
    amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), default='CZK')
    counter_account = Column(String(100), nullable=True)
    counter_name = Column(String(255), nullable=True)
    vs = Column(String(50), nullable=True)  # Variable symbol
    note = Column(Text, nullable=True)
    type = Column(String(20), nullable=True)  # expense/income/fee
    raw_type = Column(String(100), nullable=True)  # Original type from Fio
    status = Column(String(20), default='unmatched')  # unmatched/matched/known/skipped
    known_rule_id = Column(Integer, ForeignKey("known_transactions.id"), nullable=True)
    skip_reason = Column(String(255), nullable=True)  # If manually skipped
    extracted_vendor = Column(String(255), nullable=True)  # LLM-extracted vendor for card transactions
    fetched_at = Column(DateTime, default=datetime.utcnow)


class KnownTransaction(Base):
    """Known transaction rules for automatic matching (fees, recurring, etc.)."""

    __tablename__ = "known_transactions"

    id = Column(Integer, primary_key=True, index=True)
    rule_type = Column(String(20), nullable=False)  # 'exact', 'pattern', 'vendor', 'note', 'account'
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


class VendorAlias(Base):
    """Learned vendor name mappings from approved matches."""

    __tablename__ = "vendor_aliases"

    id = Column(Integer, primary_key=True, index=True)
    # Vendor name from transaction (counter_name or extracted from note)
    transaction_vendor = Column(String(255), nullable=False, index=True)
    # Vendor name from invoice (from filename/PDF)
    invoice_vendor = Column(String(255), nullable=False, index=True)
    # How this alias was learned
    source = Column(String(50), nullable=False)  # 'manual_match', 'auto_match'
    # Number of times this mapping has been confirmed
    confidence_count = Column(Integer, default=1, nullable=False)
    # When this was first learned
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # Last time this mapping was confirmed
    last_confirmed_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PDFCache(Base):
    """Cache for PDF files downloaded from Google Drive."""

    __tablename__ = "pdf_cache"

    id = Column(Integer, primary_key=True, index=True)
    gdrive_file_id = Column(String(255), unique=True, nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    content = Column(LargeBinary, nullable=False)
    file_size = Column(Integer, nullable=False)
    md5_checksum = Column(String(32), nullable=True)
    cached_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_accessed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
