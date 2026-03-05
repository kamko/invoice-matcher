"""Main matching orchestrator for transaction-invoice reconciliation."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from models.invoice import Invoice
from models.transaction import Transaction
from .strategies import (
    MatchStrategy,
    AmountStrategy,
    VendorStrategy,
    DateStrategy,
    VSStrategy,
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

    def __init__(self):
        self.strategies: List[MatchStrategy] = [
            AmountStrategy(),
            VendorStrategy(),
            DateStrategy(),
            VSStrategy(),
        ]

    def match_all(
        self,
        transactions: List[Transaction],
        invoices: List[Invoice]
    ) -> Tuple[List[MatchResult], List[Transaction], List[Invoice]]:
        """
        Match all transactions to invoices using best-match-first algorithm.

        Args:
            transactions: List of bank transactions
            invoices: List of invoices

        Returns:
            Tuple of (matched results, unmatched transactions, unmatched invoices)
        """
        # Filter out fee transactions
        matchable_transactions = [t for t in transactions if not t.is_fee]

        # Calculate all possible match scores
        all_matches: List[MatchResult] = []

        for transaction in matchable_transactions:
            for invoice in invoices:
                if not self._is_compatible(transaction, invoice):
                    continue

                score, strategy_scores = self._calculate_match_score(transaction, invoice)
                if score >= 0.30:  # Only consider reasonable matches
                    all_matches.append(MatchResult(
                        transaction=transaction,
                        invoice=invoice,
                        confidence=score,
                        strategy_scores=strategy_scores
                    ))

        # Sort by confidence descending (best matches first)
        all_matches.sort(key=lambda m: m.confidence, reverse=True)

        # Greedily assign matches, highest confidence first
        matched_results: List[MatchResult] = []
        matched_transactions: set = set()
        matched_invoices: set = set()

        for match in all_matches:
            trans_id = match.transaction.id
            inv_path = str(match.invoice.file_path)

            # Skip if either already matched
            if trans_id in matched_transactions or inv_path in matched_invoices:
                continue

            matched_results.append(match)
            matched_transactions.add(trans_id)
            matched_invoices.add(inv_path)

        # Find unmatched transactions and invoices
        unmatched_transactions = [
            t for t in matchable_transactions
            if t.id not in matched_transactions
        ]
        unmatched_invoices = [
            inv for inv in invoices
            if str(inv.file_path) not in matched_invoices
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
