"""Matching strategies for transaction-invoice reconciliation."""

import re
from abc import ABC, abstractmethod
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from rapidfuzz import fuzz

from models.invoice import Invoice
from models.transaction import Transaction
from parsers.csv_parser import extract_vendor_from_note
from parsers.llm_extractor import score_transaction_invoice_match


class MatchStrategy(ABC):
    """Base class for matching strategies."""

    @property
    @abstractmethod
    def weight(self) -> float:
        """Return the weight of this strategy (0.0 to 1.0)."""
        pass

    @abstractmethod
    def score(self, transaction: Transaction, invoice: Invoice) -> float:
        """
        Calculate match score between transaction and invoice.

        Returns:
            Score between 0.0 (no match) and 1.0 (perfect match)
        """
        pass


class AmountStrategy(MatchStrategy):
    """Match based on transaction amount vs invoice amount."""

    TOLERANCE = Decimal("0.05")  # 5 cent tolerance

    @property
    def weight(self) -> float:
        return 0.40

    def score(self, transaction: Transaction, invoice: Invoice) -> float:
        if invoice.amount is None:
            return 0.0

        trans_amt = transaction.abs_amount
        inv_amt = abs(invoice.amount)  # Use absolute value for comparison

        diff = abs(trans_amt - inv_amt)

        if diff <= self.TOLERANCE:
            return 1.0

        # Partial score for close matches (within 5%)
        max_amt = max(trans_amt, inv_amt)
        if max_amt == 0:
            return 0.0
        pct_diff = float(diff / max_amt)
        if pct_diff <= 0.05:
            return 1.0 - pct_diff

        return 0.0


class VendorStrategy(MatchStrategy):
    """Match based on vendor name similarity using LLM comparison."""

    # Enable debug logging
    DEBUG = False

    @property
    def weight(self) -> float:
        return 0.25

    def score(self, transaction: Transaction, invoice: Invoice) -> float:
        # Extract vendor from transaction note (regex-based)
        trans_vendor = extract_vendor_from_note(transaction.note).lower()
        inv_vendor = invoice.vendor.lower().replace("-", " ")

        if not inv_vendor:
            return 0.0

        # Try LLM extraction if regex extraction is weak
        if not trans_vendor or len(trans_vendor) < 3:
            try:
                from parsers.llm_extractor import get_vendor_from_note_cached
                llm_vendor = get_vendor_from_note_cached(transaction.note)
                if llm_vendor:
                    trans_vendor = llm_vendor
            except Exception:
                pass

        if not trans_vendor:
            # No vendor info available - return neutral score
            # This happens for wire transfers with empty notes
            return 0.5

        # Quick check: if one contains the other, it's a match
        if inv_vendor in trans_vendor or trans_vendor in inv_vendor:
            if self.DEBUG:
                print(f"  [VENDOR] substring match: '{trans_vendor}' ~ '{inv_vendor}' = 1.0")
            return 1.0

        # Use LLM for vendor comparison (cached)
        # LLM returns 1.0 for YES (same company) and 0.0 for NO (different)
        try:
            from parsers.llm_extractor import compare_vendors_llm
            llm_score = compare_vendors_llm(trans_vendor, inv_vendor)
            # LLM gave us an answer - use it directly (even if 0.0)
            # Do NOT fall back to fuzzy matching - trust the LLM
            if self.DEBUG:
                print(f"  [VENDOR] LLM: '{trans_vendor}' ~ '{inv_vendor}' = {llm_score}")
            return llm_score
        except RuntimeError as e:
            # LLM unavailable - fall back to fuzzy matching
            if self.DEBUG:
                print(f"  [VENDOR] LLM unavailable ({e}), using fuzzy")
        except Exception as e:
            # Unexpected error - log and fall back
            print(f"LLM vendor comparison error: {e}")

        # Fallback to fuzzy matching only if LLM API completely fails
        simple_ratio = fuzz.ratio(trans_vendor, inv_vendor)
        token_ratio = fuzz.token_set_ratio(trans_vendor, inv_vendor)
        best_ratio = max(simple_ratio, token_ratio)

        if self.DEBUG:
            print(f"  [VENDOR] fuzzy: '{trans_vendor}' ~ '{inv_vendor}' = {best_ratio/100.0}")

        return best_ratio / 100.0


class DateStrategy(MatchStrategy):
    """Match based on date proximity."""

    DAYS_BEFORE = 30  # Invoice can be up to 30 days before transaction
    DAYS_AFTER = 3    # Invoice can be up to 3 days after (processing delay)

    @property
    def weight(self) -> float:
        return 0.20

    def score(self, transaction: Transaction, invoice: Invoice) -> float:
        trans_date = transaction.date
        inv_date = invoice.invoice_date

        # delta > 0 means invoice is BEFORE transaction
        # delta < 0 means invoice is AFTER transaction
        delta = (trans_date - inv_date).days

        # Invoice is AFTER transaction - only allow small processing delay
        if delta < -self.DAYS_AFTER:
            return 0.0

        # Invoice is too old (more than 30 days before transaction)
        if delta > self.DAYS_BEFORE:
            return 0.0

        # Perfect match: invoice same day or 1-2 days before
        if 0 <= delta <= 2:
            return 1.0

        # Invoice is 1-3 days after transaction (processing delay) - acceptable
        if -self.DAYS_AFTER <= delta < 0:
            return 0.8

        # Good match: invoice within a week before
        if delta <= 7:
            return 0.9

        # Acceptable: within 2 weeks before
        if delta <= 14:
            return 0.7

        # Older but acceptable
        return 0.5


class VSStrategy(MatchStrategy):
    """Match based on Variable Symbol."""

    @property
    def weight(self) -> float:
        return 0.15

    def score(self, transaction: Transaction, invoice: Invoice) -> float:
        trans_vs = transaction.vs.strip()

        # For wire transfers, VS is a strong matching signal
        if transaction.is_wire and invoice.is_wire:
            # Try invoice VS first
            if invoice.vs:
                inv_vs = invoice.vs.strip()
                if trans_vs and inv_vs:
                    if trans_vs == inv_vs:
                        return 1.0
                    # Check if one contains the other
                    if trans_vs in inv_vs or inv_vs in trans_vs:
                        return 0.8

            # Try matching against invoice number
            inv_num = invoice.invoice_number.replace("-", "")
            if trans_vs and inv_num:
                if trans_vs == inv_num:
                    return 1.0
                # Check sequence number part
                parts = invoice.invoice_number.split("-")
                if len(parts) >= 4:
                    seq = parts[-1]  # e.g., "001"
                    if trans_vs.endswith(seq) or seq in trans_vs:
                        return 0.5

            # Wire transfer without VS match - low score
            return 0.0

        # For card transactions, VS is not used
        if transaction.is_card:
            return 0.5  # Neutral - don't penalize or reward

        return 0.0


class LLMStrategy(MatchStrategy):
    """Use LLM to score the match based on all available context."""

    @property
    def weight(self) -> float:
        return 1.0  # LLM does all scoring

    def score(self, transaction: Transaction, invoice: Invoice) -> float:
        return score_transaction_invoice_match(
            trans_date=str(transaction.date),
            trans_amount=str(transaction.amount),
            trans_note=transaction.note or "",
            trans_counter_name=transaction.counter_name or "",
            trans_counter_account=transaction.counter_account or "",
            trans_vs=transaction.vs or "",
            trans_type=transaction.transaction_type,
            inv_filename=invoice.filename,
            inv_date=str(invoice.invoice_date),
            inv_amount=str(invoice.amount) if invoice.amount else "",
            inv_vendor=invoice.vendor,
            inv_vs=invoice.vs or "",
            inv_type=invoice.payment_type,
        )
