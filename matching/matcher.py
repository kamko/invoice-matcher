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
        invoices: List[Invoice]
    ) -> Tuple[List[MatchResult], List[Transaction], List[Invoice]]:
        """
        Match transactions to invoices using two-phase approach:
        1. Rule-based confident matches (exact amount + good vendor score)
        2. LLM selection for remaining ambiguous cases

        Args:
            transactions: List of bank transactions
            invoices: List of invoices

        Returns:
            Tuple of (matched results, unmatched transactions, unmatched invoices)
        """
        # Filter out fee transactions
        matchable_transactions = [t for t in transactions if not t.is_fee]

        matched_results: List[MatchResult] = []
        matched_transactions: set = set()
        matched_invoices: set = set()  # (file_path, receipt_index) tuples

        # Phase 1: Rule-based confident matching
        rule_strategies = [AmountStrategy(), VendorStrategy(), DateStrategy(), VSStrategy()]

        all_matches: List[MatchResult] = []
        for transaction in matchable_transactions:
            for invoice in invoices:
                if not self._is_compatible(transaction, invoice):
                    continue

                # Calculate rule-based scores
                total_score = 0.0
                strategy_scores = {}
                for strategy in rule_strategies:
                    score = strategy.score(transaction, invoice)
                    weighted_score = score * strategy.weight
                    total_score += weighted_score
                    strategy_scores[strategy.__class__.__name__] = score

                amount_score = strategy_scores.get("AmountStrategy", 0)
                vendor_score = strategy_scores.get("VendorStrategy", 0)

                # Skip if amounts don't match at all
                if amount_score < 0.5:
                    continue

                # Confident match: exact amount + good vendor
                if amount_score >= 0.95 and vendor_score >= 0.6:
                    all_matches.append(MatchResult(
                        transaction=transaction,
                        invoice=invoice,
                        confidence=total_score,
                        strategy_scores=strategy_scores
                    ))

        # Sort by confidence and greedily assign
        all_matches.sort(key=lambda m: -m.confidence)
        for match in all_matches:
            trans_id = match.transaction.id
            inv_key = (str(match.invoice.file_path), match.invoice.receipt_index)
            if trans_id in matched_transactions or inv_key in matched_invoices:
                continue
            matched_results.append(match)
            matched_transactions.add(trans_id)
            matched_invoices.add(inv_key)

        # Phase 2: LLM selection for remaining transactions
        if self.use_llm:
            from parsers.llm_extractor import select_best_invoice_llm

            remaining_transactions = [
                t for t in matchable_transactions
                if t.id not in matched_transactions
            ]
            remaining_invoices = [
                inv for inv in invoices
                if (str(inv.file_path), inv.receipt_index) not in matched_invoices
            ]

            for transaction in remaining_transactions:
                # Find candidate invoices (compatible + amount within 10%)
                candidates = []
                candidate_invoices = []
                for invoice in remaining_invoices:
                    if not self._is_compatible(transaction, invoice):
                        continue
                    if invoice.amount is None:
                        continue
                    trans_amt = abs(transaction.amount)
                    inv_amt = abs(invoice.amount)
                    diff = abs(trans_amt - inv_amt)
                    max_amt = max(trans_amt, inv_amt)
                    if max_amt > 0 and float(diff / max_amt) <= 0.10:
                        candidates.append({
                            "filename": invoice.filename,
                            "date": str(invoice.invoice_date),
                            "amount": str(invoice.amount),
                            "vendor": invoice.vendor,
                            "type": invoice.payment_type,
                            "vs": invoice.vs or "",
                        })
                        candidate_invoices.append(invoice)

                if not candidates:
                    continue

                # Ask LLM to select
                idx, confidence = select_best_invoice_llm(
                    trans_date=str(transaction.date),
                    trans_amount=str(transaction.amount),
                    trans_note=transaction.note or "",
                    trans_counter_name=transaction.counter_name or "",
                    trans_vs=transaction.vs or "",
                    trans_type=transaction.transaction_type,
                    candidates=candidates,
                )

                if idx >= 0 and confidence >= 0.50:
                    invoice = candidate_invoices[idx]
                    inv_key = (str(invoice.file_path), invoice.receipt_index)
                    if inv_key not in matched_invoices:
                        matched_results.append(MatchResult(
                            transaction=transaction,
                            invoice=invoice,
                            confidence=confidence,
                            strategy_scores={"LLMStrategy": confidence}
                        ))
                        matched_transactions.add(transaction.id)
                        matched_invoices.add(inv_key)
                        # Remove from remaining
                        remaining_invoices = [
                            inv for inv in remaining_invoices
                            if (str(inv.file_path), inv.receipt_index) != inv_key
                        ]

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
