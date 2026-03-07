"""Simplified matching service with deterministic tiered matching."""

import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func

from web.database.models import Invoice, Transaction, VendorAlias, KnownTransaction


class MatchingService:
    """Service for matching invoices to transactions."""

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # Tier 1: Deterministic Auto-Match (100% confidence)
    # =========================================================================

    def auto_match_by_vs(self, invoice: Invoice) -> Optional[Transaction]:
        """Wire transfer with VS - exact match."""
        if not invoice.vs or invoice.payment_type != 'wire':
            return None

        transaction = self.db.query(Transaction).filter(
            Transaction.vs == invoice.vs,
            Transaction.status == 'unmatched',
            Transaction.amount < 0  # Expense
        ).first()

        return transaction

    def auto_match_by_iban_amount(self, invoice: Invoice) -> Optional[Transaction]:
        """Wire transfer with IBAN + exact amount match."""
        if not invoice.iban or invoice.payment_type != 'wire':
            return None

        transaction = self.db.query(Transaction).filter(
            Transaction.counter_account == invoice.iban,
            func.abs(Transaction.amount) == invoice.amount,
            Transaction.status == 'unmatched'
        ).first()

        return transaction

    # =========================================================================
    # Tier 2: Learned Auto-Match (vendor aliases)
    # =========================================================================

    def auto_match_by_vendor_alias(self, invoice: Invoice) -> Optional[Transaction]:
        """Card payment with known vendor mapping."""
        if not invoice.vendor:
            return None

        # Get all aliases for this invoice vendor
        aliases = self.db.query(VendorAlias).filter(
            VendorAlias.invoice_vendor == invoice.vendor.lower()
        ).all()

        if not aliases:
            return None

        trans_vendors = [a.transaction_vendor for a in aliases]

        # Find unmatched transactions matching any alias
        for transaction in self.db.query(Transaction).filter(
            Transaction.status == 'unmatched'
        ).all():
            trans_vendor = self._extract_vendor(transaction)
            if not trans_vendor:
                continue

            if trans_vendor.lower() in [v.lower() for v in trans_vendors]:
                # Check amount tolerance (5%)
                if self._amounts_match(transaction.amount, invoice.amount, tolerance=0.05):
                    # Check date range (45 days)
                    if self._dates_in_range(invoice.invoice_date, transaction.date, days=45):
                        return transaction

        return None

    # =========================================================================
    # Tier 3: Suggestions (manual confirmation needed)
    # =========================================================================

    def suggest_matches_for_invoice(
        self,
        invoice: Invoice,
        limit: int = 5
    ) -> List[Tuple[Transaction, int]]:
        """Return ranked list of potential transaction matches for an invoice."""
        candidates = []

        for transaction in self.db.query(Transaction).filter(
            Transaction.status == 'unmatched'
        ).all():
            # Check type compatibility
            if not self._is_compatible(invoice, transaction):
                continue

            score = 0

            # Amount match (50 points max)
            if invoice.amount and self._amounts_match(
                transaction.amount, invoice.amount, tolerance=0.10
            ):
                score += 50

            # Date range (30 points max)
            if invoice.invoice_date and self._dates_in_range(
                invoice.invoice_date, transaction.date, days=30
            ):
                score += 30

            # Vendor similarity (20 points max)
            if invoice.vendor:
                vendor_sim = self._vendor_similarity(
                    invoice.vendor,
                    self._extract_vendor(transaction)
                )
                if vendor_sim > 0.5:
                    score += int(20 * vendor_sim)

            if score > 0:
                candidates.append((transaction, score))

        # Sort by score descending
        candidates.sort(key=lambda x: -x[1])
        return candidates[:limit]

    def suggest_matches_for_transaction(
        self,
        transaction: Transaction,
        limit: int = 5
    ) -> List[Tuple[Invoice, int]]:
        """Return ranked list of potential invoice matches for a transaction."""
        candidates = []

        for invoice in self.db.query(Invoice).filter(
            Invoice.status == 'unmatched'
        ).all():
            # Check type compatibility
            if not self._is_compatible(invoice, transaction):
                continue

            score = 0

            # Amount match (50 points max)
            if invoice.amount and self._amounts_match(
                transaction.amount, invoice.amount, tolerance=0.10
            ):
                score += 50

            # Date range (30 points max)
            if invoice.invoice_date and self._dates_in_range(
                invoice.invoice_date, transaction.date, days=30
            ):
                score += 30

            # Vendor similarity (20 points max)
            trans_vendor = self._extract_vendor(transaction)
            if invoice.vendor and trans_vendor:
                vendor_sim = self._vendor_similarity(invoice.vendor, trans_vendor)
                if vendor_sim > 0.5:
                    score += int(20 * vendor_sim)

            if score > 0:
                candidates.append((invoice, score))

        # Sort by score descending
        candidates.sort(key=lambda x: -x[1])
        return candidates[:limit]

    # =========================================================================
    # Match Execution
    # =========================================================================

    def match_invoice_to_transaction(
        self,
        invoice_id: int,
        transaction_id: str,
        learn_alias: bool = True
    ) -> Tuple[Invoice, Transaction]:
        """Create a match. Enforces 1:1."""
        invoice = self.db.query(Invoice).filter(Invoice.id == invoice_id).first()
        transaction = self.db.query(Transaction).filter(Transaction.id == transaction_id).first()

        if not invoice:
            raise ValueError(f"Invoice {invoice_id} not found")
        if not transaction:
            raise ValueError(f"Transaction {transaction_id} not found")

        if invoice.status == 'matched':
            raise ValueError("Invoice already matched")
        if transaction.status == 'matched':
            raise ValueError("Transaction already matched")

        # Create the match
        invoice.transaction_id = transaction_id
        invoice.status = 'matched'
        transaction.status = 'matched'

        # Learn vendor alias for future
        if learn_alias and invoice.vendor:
            trans_vendor = self._extract_vendor(transaction)
            if trans_vendor:
                self._store_vendor_alias(invoice.vendor, trans_vendor)

        self.db.commit()
        return invoice, transaction

    def unmatch_invoice(self, invoice_id: int) -> Invoice:
        """Remove a match from an invoice."""
        invoice = self.db.query(Invoice).filter(Invoice.id == invoice_id).first()
        if not invoice:
            raise ValueError(f"Invoice {invoice_id} not found")

        if invoice.status != 'matched' or not invoice.transaction_id:
            raise ValueError("Invoice is not matched")

        # Find and update transaction
        transaction = self.db.query(Transaction).filter(
            Transaction.id == invoice.transaction_id
        ).first()

        invoice.transaction_id = None
        invoice.status = 'unmatched'

        if transaction:
            transaction.status = 'unmatched'

        self.db.commit()
        return invoice

    # =========================================================================
    # Batch Auto-Matching
    # =========================================================================

    def run_auto_matching(self) -> dict:
        """Run auto-matching on all unmatched invoices.

        Returns dict with counts of matches made at each tier.
        """
        results = {'tier1_vs': 0, 'tier1_iban': 0, 'tier2_alias': 0}

        unmatched_invoices = self.db.query(Invoice).filter(
            Invoice.status == 'unmatched'
        ).all()

        for invoice in unmatched_invoices:
            # Tier 1: VS match
            match = self.auto_match_by_vs(invoice)
            if match:
                self.match_invoice_to_transaction(invoice.id, match.id, learn_alias=False)
                results['tier1_vs'] += 1
                continue

            # Tier 1: IBAN + amount match
            match = self.auto_match_by_iban_amount(invoice)
            if match:
                self.match_invoice_to_transaction(invoice.id, match.id, learn_alias=False)
                results['tier1_iban'] += 1
                continue

            # Tier 2: Vendor alias match
            match = self.auto_match_by_vendor_alias(invoice)
            if match:
                self.match_invoice_to_transaction(invoice.id, match.id, learn_alias=False)
                results['tier2_alias'] += 1
                continue

        return results

    # =========================================================================
    # Known Transaction Rules
    # =========================================================================

    def apply_known_rules(self, transaction: Transaction) -> Optional[KnownTransaction]:
        """Check if transaction matches any known rule."""
        rules = self.db.query(KnownTransaction).filter(
            KnownTransaction.is_active == True
        ).all()

        for rule in rules:
            if self._matches_rule(transaction, rule):
                return rule
        return None

    def _matches_rule(self, trans: Transaction, rule: KnownTransaction) -> bool:
        """Check if transaction matches a known rule."""
        # Exact amount match
        if rule.amount is not None:
            if abs(trans.amount) != abs(rule.amount):
                return False

        # Amount range
        if rule.amount_min is not None and abs(trans.amount) < abs(rule.amount_min):
            return False
        if rule.amount_max is not None and abs(trans.amount) > abs(rule.amount_max):
            return False

        # Counter account exact match
        if rule.counter_account:
            if trans.counter_account != rule.counter_account:
                return False

        # Vendor pattern (regex)
        if rule.vendor_pattern:
            vendor = trans.counter_name or ''
            if not re.search(rule.vendor_pattern, vendor, re.IGNORECASE):
                return False

        # Note pattern (regex)
        if rule.note_pattern:
            note = trans.note or ''
            if not re.search(rule.note_pattern, note, re.IGNORECASE):
                return False

        # VS pattern
        if rule.vs_pattern:
            vs = trans.vs or ''
            if not re.search(rule.vs_pattern, vs):
                return False

        return True

    def mark_transaction_known(
        self,
        transaction_id: str,
        rule_id: int
    ) -> Transaction:
        """Mark a transaction as matching a known rule."""
        transaction = self.db.query(Transaction).filter(
            Transaction.id == transaction_id
        ).first()
        if not transaction:
            raise ValueError(f"Transaction {transaction_id} not found")

        transaction.status = 'known'
        transaction.known_rule_id = rule_id
        self.db.commit()
        return transaction

    def skip_transaction(
        self,
        transaction_id: str,
        reason: str
    ) -> Transaction:
        """Mark a transaction as skipped."""
        transaction = self.db.query(Transaction).filter(
            Transaction.id == transaction_id
        ).first()
        if not transaction:
            raise ValueError(f"Transaction {transaction_id} not found")

        transaction.status = 'skipped'
        transaction.skip_reason = reason
        self.db.commit()
        return transaction

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _extract_vendor(self, transaction: Transaction) -> Optional[str]:
        """Extract vendor name from transaction."""
        # Try counter_name first
        if transaction.counter_name and len(transaction.counter_name.strip()) > 2:
            return transaction.counter_name.strip()

        # Try to extract from note (e.g., "Nakup: Alza.cz a.s., Prague...")
        note = transaction.note or ''
        if 'Nakup:' in note or 'Nákup:' in note:
            # Extract the part after "Nakup:"
            match = re.search(r'[Nn]ákup:\s*([^,]+)', note)
            if match:
                return match.group(1).strip()

        return None

    def _amounts_match(
        self,
        trans_amount: Decimal,
        invoice_amount: Optional[Decimal],
        tolerance: float = 0.05
    ) -> bool:
        """Check if amounts match within tolerance."""
        if invoice_amount is None:
            return False

        trans_abs = abs(trans_amount)
        inv_abs = abs(invoice_amount)

        if inv_abs == 0:
            return trans_abs == 0

        diff = abs(trans_abs - inv_abs) / inv_abs
        return diff <= tolerance

    def _dates_in_range(self, invoice_date, trans_date, days: int = 30) -> bool:
        """Check if dates are within range."""
        if invoice_date is None or trans_date is None:
            return False

        diff = abs((trans_date - invoice_date).days)
        return diff <= days

    def _vendor_similarity(self, vendor1: Optional[str], vendor2: Optional[str]) -> float:
        """Calculate vendor name similarity (0.0 to 1.0)."""
        if not vendor1 or not vendor2:
            return 0.0

        v1 = vendor1.lower().strip()
        v2 = vendor2.lower().strip()

        # Exact match
        if v1 == v2:
            return 1.0

        # One contains the other
        if v1 in v2 or v2 in v1:
            return 0.8

        # Simple word overlap
        words1 = set(re.findall(r'\w+', v1))
        words2 = set(re.findall(r'\w+', v2))

        if not words1 or not words2:
            return 0.0

        common = words1 & words2
        return len(common) / max(len(words1), len(words2))

    def _is_compatible(self, invoice: Invoice, transaction: Transaction) -> bool:
        """Check if invoice and transaction types are compatible."""
        # Credit notes match with positive (income) transactions only
        if invoice.is_credit_note:
            return transaction.amount > 0

        # Regular invoices match with negative (expense) transactions
        if transaction.amount > 0:
            return False

        # Type compatibility
        if invoice.payment_type == 'card' and transaction.type == 'card':
            return True
        if invoice.payment_type == 'wire' and transaction.type == 'wire':
            return True

        # Allow matching if types are unknown
        if transaction.type not in ('card', 'wire', 'fee'):
            return True

        return False

    def _store_vendor_alias(self, invoice_vendor: str, transaction_vendor: str):
        """Store or update a vendor alias mapping."""
        inv_vendor = invoice_vendor.lower().strip()
        trans_vendor = transaction_vendor.lower().strip()

        existing = self.db.query(VendorAlias).filter(
            VendorAlias.invoice_vendor == inv_vendor,
            VendorAlias.transaction_vendor == trans_vendor
        ).first()

        if existing:
            existing.confidence_count += 1
            existing.last_confirmed_at = datetime.utcnow()
        else:
            alias = VendorAlias(
                invoice_vendor=inv_vendor,
                transaction_vendor=trans_vendor,
                source='manual_match',
                confidence_count=1,
                created_at=datetime.utcnow(),
                last_confirmed_at=datetime.utcnow()
            )
            self.db.add(alias)

        self.db.commit()
