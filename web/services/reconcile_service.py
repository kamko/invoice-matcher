"""Service for running reconciliation."""

from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple
import tempfile
import shutil

from sqlalchemy.orm import Session

from web.database.models import ReconciliationSession, MonthlyReconciliation
from web.schemas.reconciliation import ReconcileRequest, MonthlyReconcileRequest
from web.services.known_trans_service import KnownTransactionService
from web.config import DATA_DIR

from models.transaction import Transaction
from models.invoice import Invoice
from parsers.fio_api import fetch_transactions_from_api
from parsers.pdf_parser import parse_invoices
from matching.matcher import Matcher, MatchResult


class ReconcileService:
    """Service for running reconciliation operations."""

    def __init__(self, db: Session):
        self.db = db
        self.known_service = KnownTransactionService(db)

    def create_session(self, request: ReconcileRequest) -> ReconciliationSession:
        """Create a new reconciliation session."""
        session = ReconciliationSession(
            from_date=datetime.combine(request.from_date, datetime.min.time()),
            to_date=datetime.combine(request.to_date, datetime.min.time()),
            gdrive_folder_id=request.gdrive_folder_id,
            status="pending"
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def get_session(self, session_id: int) -> ReconciliationSession | None:
        """Get a reconciliation session by ID."""
        return self.db.query(ReconciliationSession).filter(
            ReconciliationSession.id == session_id
        ).first()

    def run_reconciliation(
        self,
        session: ReconciliationSession,
        fio_token: str,
        invoice_dir: Path | None = None
    ) -> ReconciliationSession:
        """Run the full reconciliation process."""
        try:
            session.status = "processing"
            self.db.commit()

            # Fetch transactions from Fio API
            transactions = fetch_transactions_from_api(
                token=fio_token.strip(),
                from_date=session.from_date.date(),
                to_date=session.to_date.date()
            )

            # Parse invoices
            if invoice_dir and invoice_dir.exists():
                invoices = parse_invoices(invoice_dir)
            else:
                invoices = []

            # Separate known transactions
            known_transactions = []
            unknown_transactions = []

            for trans in transactions:
                if trans.is_fee:
                    continue  # Skip fees

                rule = self.known_service.match_transaction(trans)
                if rule:
                    known_transactions.append((trans, rule))
                    self.known_service.record_match(rule, trans, session.id)
                else:
                    unknown_transactions.append(trans)

            # Run matcher on unknown transactions only
            matcher = Matcher()
            matched, unmatched_trans, unmatched_inv = matcher.match_all(
                unknown_transactions,
                invoices
            )

            # Store results
            results = self._serialize_results(
                matched, unmatched_trans, unmatched_inv, known_transactions
            )

            session.results_json = results
            session.matched_count = len([m for m in matched if m.status == "OK"])
            session.review_count = len([m for m in matched if m.status == "REVIEW"])
            session.unmatched_count = len(unmatched_trans)
            session.known_count = len(known_transactions)
            session.status = "completed"
            session.completed_at = datetime.utcnow()
            session.error_message = None

            self.db.commit()
            self.db.refresh(session)

            return session

        except Exception as e:
            session.status = "failed"
            session.error_message = str(e)
            self.db.commit()
            raise

    def _serialize_results(
        self,
        matched: List[MatchResult],
        unmatched_trans: List[Transaction],
        unmatched_inv: List[Invoice],
        known_transactions: List[Tuple[Transaction, Any]]
    ) -> Dict[str, Any]:
        """Serialize results to JSON-compatible format."""
        return {
            "matched": [
                {
                    "transaction": self._serialize_transaction(m.transaction),
                    "invoice": self._serialize_invoice(m.invoice) if m.invoice else None,
                    "confidence": m.confidence,
                    "confidence_pct": m.confidence_pct,
                    "status": m.status,
                    "strategy_scores": m.strategy_scores,
                }
                for m in matched
            ],
            "unmatched": [
                self._serialize_transaction(t) for t in unmatched_trans
            ],
            "unmatched_invoices": [
                self._serialize_invoice(inv) for inv in unmatched_inv
            ],
            "known": [
                {
                    **self._serialize_transaction(t),
                    "rule_reason": rule.reason,
                }
                for t, rule in known_transactions
            ],
        }

    def _serialize_transaction(self, t: Transaction) -> Dict[str, Any]:
        """Serialize a Transaction to dict."""
        return {
            "id": t.id,
            "date": str(t.date),
            "amount": str(t.amount),
            "currency": t.currency,
            "counter_account": t.counter_account or "",
            "counter_name": t.counter_name or "",
            "vs": t.vs or "",
            "note": t.note or "",
            "transaction_type": t.transaction_type,
        }

    def _serialize_invoice(self, inv: Invoice) -> Dict[str, Any]:
        """Serialize an Invoice to dict."""
        return {
            "file_path": str(inv.file_path),
            "filename": inv.filename,
            "invoice_date": str(inv.invoice_date),
            "invoice_number": inv.invoice_number,
            "payment_type": inv.payment_type,
            "vendor": inv.vendor,
            "amount": str(inv.amount) if inv.amount else None,
            "vs": inv.vs,
            "is_credit_note": inv.is_credit_note,
            "is_cash": inv.is_cash,
        }

    def get_session_results(self, session: ReconciliationSession) -> Dict[str, Any]:
        """Get formatted results for a session."""
        if not session.results_json:
            return {
                "matched": [],
                "unmatched": [],
                "unmatched_invoices": [],
                "known": [],
            }
        return session.results_json

    # ===== Monthly Reconciliation Methods =====

    def get_or_create_month(self, year_month: str, gdrive_folder_id: str | None = None) -> MonthlyReconciliation:
        """Get existing month or create new one."""
        month = self.db.query(MonthlyReconciliation).filter(
            MonthlyReconciliation.year_month == year_month
        ).first()

        if not month:
            month = MonthlyReconciliation(
                year_month=year_month,
                gdrive_folder_id=gdrive_folder_id,
                status="pending"
            )
            self.db.add(month)
            self.db.commit()
            self.db.refresh(month)
        elif gdrive_folder_id and month.gdrive_folder_id != gdrive_folder_id:
            month.gdrive_folder_id = gdrive_folder_id
            self.db.commit()

        return month

    def get_month(self, year_month: str) -> MonthlyReconciliation | None:
        """Get monthly reconciliation by year-month."""
        return self.db.query(MonthlyReconciliation).filter(
            MonthlyReconciliation.year_month == year_month
        ).first()

    def list_months(self) -> List[MonthlyReconciliation]:
        """List all monthly reconciliations."""
        return self.db.query(MonthlyReconciliation).order_by(
            MonthlyReconciliation.year_month.desc()
        ).all()

    def run_monthly_reconciliation(
        self,
        month: MonthlyReconciliation,
        fio_token: str,
        invoice_dir: Path | None = None,
        prev_month_invoice_dir: Path | None = None
    ) -> MonthlyReconciliation:
        """Run reconciliation for a specific month.

        Args:
            month: The month to reconcile
            fio_token: Fio Bank API token
            invoice_dir: Directory with invoices for this month
            prev_month_invoice_dir: Directory with invoices from previous month
                                   (for late payments)
        """
        from calendar import monthrange

        try:
            month.status = "processing"
            self.db.commit()

            # Parse year-month to get date range
            year, mon = map(int, month.year_month.split("-"))
            from_date = datetime(year, mon, 1).date()
            last_day = monthrange(year, mon)[1]
            to_date = datetime(year, mon, last_day).date()

            # Fetch transactions from Fio API
            transactions = fetch_transactions_from_api(
                token=fio_token.strip(),
                from_date=from_date,
                to_date=to_date
            )

            # Parse invoices from current month
            invoices = []
            if invoice_dir and invoice_dir.exists():
                invoices = parse_invoices(invoice_dir)
                print(f"[RECONCILE] Parsed {len(invoices)} invoices from current month: {invoice_dir}")

            # Also include previous month's invoices (for late payments)
            if prev_month_invoice_dir and prev_month_invoice_dir.exists():
                prev_invoices = parse_invoices(prev_month_invoice_dir)
                print(f"[RECONCILE] Parsed {len(prev_invoices)} invoices from prev month: {prev_month_invoice_dir}")
                invoices.extend(prev_invoices)

            print(f"[RECONCILE] Total invoices: {len(invoices)}, transactions: {len(transactions)}")

            # Separate by type: fees, income, known, unknown
            fee_transactions = []
            income_transactions = []
            known_transactions = []
            unknown_transactions = []

            for trans in transactions:
                if trans.is_fee:
                    fee_transactions.append(trans)
                    continue

                if trans.amount > 0:
                    income_transactions.append(trans)
                    continue

                rule = self.known_service.match_transaction(trans)
                if rule:
                    known_transactions.append((trans, rule))
                else:
                    unknown_transactions.append(trans)

            # Separate credit-note invoices from regular invoices
            credit_note_invoices = [inv for inv in invoices if inv.is_credit_note]
            regular_invoices = [inv for inv in invoices if not inv.is_credit_note]

            # Run matcher on unknown transactions vs regular invoices
            # Two-pass: same-month first, then previous-month as last resort
            matcher = Matcher()
            matched, unmatched_trans, unmatched_regular_inv = matcher.match_all(
                unknown_transactions,
                regular_invoices,
                year_month=month.year_month
            )

            # Match credit-note invoices with income transactions
            credit_matched, unmatched_income, unmatched_credit_inv = matcher.match_all(
                income_transactions,
                credit_note_invoices,
                year_month=month.year_month
            )

            # Combine results
            all_matched = matched + credit_matched
            all_unmatched_inv = unmatched_regular_inv + unmatched_credit_inv

            # Store results
            results = self._serialize_results(
                all_matched, unmatched_trans, all_unmatched_inv, known_transactions
            )
            results["fees"] = [self._serialize_transaction(t) for t in fee_transactions]
            results["income"] = [self._serialize_transaction(t) for t in unmatched_income]  # Only unmatched income

            month.results_json = results
            month.matched_count = len([m for m in all_matched if m.status == "OK"])
            month.review_count = len([m for m in all_matched if m.status == "REVIEW"])
            month.unmatched_count = len(unmatched_trans)
            month.known_count = len(known_transactions)
            month.fee_count = len(fee_transactions)
            month.income_count = len(unmatched_income)  # Only unmatched income
            month.status = "completed"
            month.last_synced_at = datetime.utcnow()
            month.error_message = None

            self.db.commit()
            self.db.refresh(month)

            return month

        except Exception as e:
            month.status = "failed"
            month.error_message = str(e)
            self.db.commit()
            raise

    def get_month_results(self, month: MonthlyReconciliation) -> Dict[str, Any]:
        """Get formatted results for a month."""
        if not month.results_json:
            return {
                "matched": [],
                "unmatched": [],
                "unmatched_invoices": [],
                "known": [],
                "fees": [],
                "income": [],
            }

        results = month.results_json.copy()

        # Enrich known transactions with rule_reason if missing
        known = results.get("known", [])
        if known:
            enriched_known = []
            for trans in known:
                if not trans.get("rule_reason"):
                    try:
                        # Try to find matching rule
                        from models.transaction import Transaction as TransModel
                        from decimal import Decimal
                        from datetime import date as date_type
                        # Parse date
                        date_val = trans.get("date")
                        if isinstance(date_val, str):
                            date_val = date_type.fromisoformat(date_val)
                        t = TransModel(
                            id=trans.get("id", ""),
                            date=date_val,
                            amount=Decimal(str(trans.get("amount", 0))),
                            currency=trans.get("currency", "EUR"),
                            counter_account=trans.get("counter_account"),
                            counter_name=trans.get("counter_name"),
                            vs=trans.get("vs"),
                            note=trans.get("note"),
                            transaction_type=trans.get("transaction_type", "unknown"),
                            raw_type=trans.get("raw_type", ""),
                        )
                        rule = self.known_service.match_transaction(t)
                        if rule:
                            trans = {**trans, "rule_reason": rule.reason}
                    except Exception as e:
                        print(f"Error enriching known transaction: {e}")
                enriched_known.append(trans)
            results["known"] = enriched_known

        return results

