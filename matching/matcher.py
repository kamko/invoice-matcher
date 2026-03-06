"""Main matching orchestrator for transaction-invoice reconciliation."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from models.invoice import Invoice
from models.transaction import Transaction
from .strategies import (
    MatchStrategy,
    AmountStrategy,
    VendorStrategy,
    DateStrategy,
    VSStrategy,
    LLMStrategy,
)


@dataclass
class MatchResult:
    """Result of matching a transaction to an invoice."""

    transaction: Transaction
    invoice: Optional[Invoice]
    confidence: float  # 0.0 to 1.0
    strategy_scores: Dict[str, float]  # Individual strategy scores

    @property
    def status(self) -> str:
        """Get match status based on confidence."""
        if self.confidence >= 0.70:
            return "OK"
        elif self.confidence >= 0.30:
            return "REVIEW"
        else:
            return "NO_MATCH"

    @property
    def confidence_pct(self) -> int:
        """Get confidence as percentage."""
        return int(self.confidence * 100)


class Matcher:
    """Orchestrates matching between transactions and invoices."""

    def __init__(self, use_llm: bool = True):
        """
        Initialize matcher.

        Args:
            use_llm: If True, use LLM for scoring (smarter but slower).
                    If False, use weighted rule-based strategies.
        """
        self.use_llm = use_llm
        if use_llm:
            self.strategies: List[MatchStrategy] = [LLMStrategy()]
        else:
            self.strategies: List[MatchStrategy] = [
                AmountStrategy(),
                VendorStrategy(),
                DateStrategy(),
                VSStrategy(),
            ]

    def match_all(
        self,
        transactions: List[Transaction],
        invoices: List[Invoice],
        year_month: str = None
    ) -> Tuple[List[MatchResult], List[Transaction], List[Invoice]]:
        """
        Match transactions to invoices using two-pass approach:
        1. First pass: Match with same-month invoices only
        2. Second pass: Match remaining with previous-month invoices (last resort)

        Args:
            transactions: List of bank transactions
            invoices: List of invoices
            year_month: Current month being processed (YYYY-MM format)

        Returns:
            Tuple of (matched results, unmatched transactions, unmatched invoices)
        """
        # Filter out fee transactions
        matchable_transactions = [t for t in transactions if not t.is_fee]

        matched_results: List[MatchResult] = []
        matched_transactions: set = set()
        matched_invoices: set = set()  # (file_path, receipt_index) tuples

        # Separate invoices by source month
        same_month_invoices = []
        prev_month_invoices = []
        for inv in invoices:
            source_month = getattr(inv, 'source_month', year_month)
            if source_month == year_month:
                same_month_invoices.append(inv)
            else:
                prev_month_invoices.append(inv)

        # Helper to find matches for a set of invoices
        def find_matches(trans_list: List[Transaction], inv_list: List[Invoice]) -> List[MatchResult]:
            matches = []
            amount_strategy = AmountStrategy()
            vendor_strategy = VendorStrategy()

            for transaction in trans_list:
                if transaction.id in matched_transactions:
                    continue

                for invoice in inv_list:
                    inv_key = (str(invoice.file_path), invoice.receipt_index)
                    if inv_key in matched_invoices:
                        continue
                    if not self._is_compatible(transaction, invoice):
                        continue

                    amount_score = amount_strategy.score(transaction, invoice)
                    vendor_score = vendor_strategy.score(transaction, invoice)

                    # Confident match: exact amount + reasonable vendor
                    if amount_score >= 0.95 and vendor_score >= 0.5:
                        matches.append(MatchResult(
                            transaction=transaction,
                            invoice=invoice,
                            confidence=0.9 if vendor_score >= 0.7 else 0.7,
                            strategy_scores={
                                "AmountStrategy": amount_score,
                                "VendorStrategy": vendor_score
                            }
                        ))
            return matches

        # Pass 1: Match with same-month invoices (preferred)
        same_month_matches = find_matches(matchable_transactions, same_month_invoices)
        # Sort by vendor score to prefer better matches
        same_month_matches.sort(key=lambda m: -m.strategy_scores.get("VendorStrategy", 0))

        for match in same_month_matches:
            trans_id = match.transaction.id
            inv_key = (str(match.invoice.file_path), match.invoice.receipt_index)
            if trans_id in matched_transactions or inv_key in matched_invoices:
                continue
            matched_results.append(match)
            matched_transactions.add(trans_id)
            matched_invoices.add(inv_key)

        # Pass 2: Match remaining with previous-month invoices (last resort)
        remaining_transactions = [t for t in matchable_transactions if t.id not in matched_transactions]
        prev_month_matches = find_matches(remaining_transactions, prev_month_invoices)
        prev_month_matches.sort(key=lambda m: -m.strategy_scores.get("VendorStrategy", 0))

        for match in prev_month_matches:
            trans_id = match.transaction.id
            inv_key = (str(match.invoice.file_path), match.invoice.receipt_index)
            if trans_id in matched_transactions or inv_key in matched_invoices:
                continue
            # Mark as REVIEW since it's cross-month
            match.confidence = 0.6  # Will show as REVIEW status
            match.strategy_scores["CrossMonth"] = 1.0
            matched_results.append(match)
            matched_transactions.add(trans_id)
            matched_invoices.add(inv_key)

        # Find final unmatched
        unmatched_transactions = [
            t for t in matchable_transactions
            if t.id not in matched_transactions
        ]
        unmatched_invoices = [
            inv for inv in invoices
            if (str(inv.file_path), inv.receipt_index) not in matched_invoices
        ]

        return matched_results, unmatched_transactions, unmatched_invoices

    def _is_compatible(self, transaction: Transaction, invoice: Invoice) -> bool:
        """Check if transaction and invoice types are compatible.

        Credit notes (refunds) must match with positive transactions (income).
        Regular invoices must match with negative transactions (expenses).
        """
        # Credit notes match with positive (income) transactions only
        if invoice.is_credit_note:
            if transaction.amount <= 0:
                return False  # Credit notes need positive transactions
            # Credit note refunds often come back via different channels
            # (e.g., card purchase refunded via wire transfer)
            # So be lenient on type matching for credit notes - just check amount sign
            return True

        # Regular invoices match with negative (expense) transactions only
        if transaction.amount > 0:
            return False  # Regular invoices need negative transactions

        # Type compatibility checks
        if transaction.is_card and invoice.is_card:
            return True
        if transaction.is_wire and invoice.is_wire:
            return True

        # Fallback: if transaction type is unknown/other, allow matching
        # and let the scoring strategies determine compatibility
        if transaction.transaction_type not in ("card", "wire", "fee"):
            return True

        return False

    def _find_best_match(
        self,
        transaction: Transaction,
        invoices: List[Invoice]
    ) -> Optional[MatchResult]:
        """Find the best matching invoice for a transaction."""
        best_result: Optional[MatchResult] = None
        best_score = 0.0

        for invoice in invoices:
            score, strategy_scores = self._calculate_match_score(transaction, invoice)

            if score > best_score:
                best_score = score
                best_result = MatchResult(
                    transaction=transaction,
                    invoice=invoice,
                    confidence=score,
                    strategy_scores=strategy_scores
                )

        return best_result

    def _calculate_match_score(
        self,
        transaction: Transaction,
        invoice: Invoice
    ) -> Tuple[float, Dict[str, float]]:
        """Calculate weighted match score between transaction and invoice."""
        total_score = 0.0
        strategy_scores = {}

        for strategy in self.strategies:
            score = strategy.score(transaction, invoice)
            weighted_score = score * strategy.weight
            total_score += weighted_score
            strategy_scores[strategy.__class__.__name__] = score

        return total_score, strategy_scores
