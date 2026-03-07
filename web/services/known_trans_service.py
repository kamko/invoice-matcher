"""Service for managing known transaction rules."""

import re
from decimal import Decimal
from typing import List, Optional, Union

from sqlalchemy.orm import Session

from web.database.models import KnownTransaction, Transaction as TransactionModel
from web.schemas.known_transaction import KnownTransactionCreate, KnownTransactionUpdate


class KnownTransactionService:
    """Service for CRUD operations on known transaction rules."""

    def __init__(self, db: Session):
        self.db = db

    def get_all(self, active_only: bool = False) -> List[KnownTransaction]:
        """Get all known transaction rules."""
        query = self.db.query(KnownTransaction)
        if active_only:
            query = query.filter(KnownTransaction.is_active == True)
        return query.order_by(KnownTransaction.created_at.desc()).all()

    def get_by_id(self, rule_id: int) -> Optional[KnownTransaction]:
        """Get a known transaction rule by ID."""
        return self.db.query(KnownTransaction).filter(
            KnownTransaction.id == rule_id
        ).first()

    def create(self, data: KnownTransactionCreate) -> KnownTransaction:
        """Create a new known transaction rule."""
        rule = KnownTransaction(**data.model_dump())
        self.db.add(rule)
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def update(self, rule_id: int, data: KnownTransactionUpdate) -> Optional[KnownTransaction]:
        """Update a known transaction rule."""
        rule = self.get_by_id(rule_id)
        if not rule:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(rule, key, value)

        self.db.commit()
        self.db.refresh(rule)
        return rule

    def delete(self, rule_id: int) -> bool:
        """Delete a known transaction rule."""
        rule = self.get_by_id(rule_id)
        if not rule:
            return False

        self.db.delete(rule)
        self.db.commit()
        return True

    def match_transaction(self, transaction: Union[TransactionModel, 'Transaction']) -> Optional[KnownTransaction]:
        """Check if a transaction matches any known transaction rule."""
        rules = self.get_all(active_only=True)

        for rule in rules:
            if self._matches_rule(transaction, rule):
                return rule

        return None

    def _matches_rule(self, transaction, rule: KnownTransaction) -> bool:
        """Check if a transaction matches a specific rule."""
        if rule.rule_type == "exact":
            return self._matches_exact(transaction, rule)
        elif rule.rule_type == "pattern":
            return self._matches_pattern(transaction, rule)
        elif rule.rule_type == "vendor":
            return self._matches_vendor(transaction, rule)
        elif rule.rule_type == "note":
            return self._matches_note(transaction, rule)
        elif rule.rule_type == "account":
            return self._matches_account(transaction, rule)
        return False

    def _get_amount(self, transaction) -> Decimal:
        """Get amount from transaction (works with both model types)."""
        return Decimal(str(transaction.amount))

    def _get_counter_account(self, transaction) -> str:
        """Get counter account from transaction."""
        return getattr(transaction, 'counter_account', '') or ''

    def _get_counter_name(self, transaction) -> str:
        """Get counter name from transaction."""
        return getattr(transaction, 'counter_name', '') or ''

    def _get_vs(self, transaction) -> str:
        """Get variable symbol from transaction."""
        return getattr(transaction, 'vs', '') or ''

    def _get_note(self, transaction) -> str:
        """Get note from transaction."""
        return getattr(transaction, 'note', '') or ''

    def _matches_exact(self, transaction, rule: KnownTransaction) -> bool:
        """Check exact match (amount + counter_account or VS)."""
        if rule.amount is not None:
            if abs(self._get_amount(transaction)) != abs(rule.amount):
                return False

        if rule.counter_account:
            if self._get_counter_account(transaction) != rule.counter_account:
                return False

        if rule.vs_pattern:
            if self._get_vs(transaction) != rule.vs_pattern:
                return False

        # At least one criteria must be specified
        return bool(rule.amount or rule.counter_account or rule.vs_pattern)

    def _matches_pattern(self, transaction, rule: KnownTransaction) -> bool:
        """Check pattern match using regex."""
        amount = self._get_amount(transaction)

        # Amount range check
        if rule.amount_min is not None and abs(amount) < rule.amount_min:
            return False
        if rule.amount_max is not None and abs(amount) > rule.amount_max:
            return False

        # Vendor pattern
        if rule.vendor_pattern:
            pattern = re.compile(rule.vendor_pattern, re.IGNORECASE)
            text_to_match = f"{self._get_counter_name(transaction)} {self._get_note(transaction)}"
            if not pattern.search(text_to_match):
                return False

        # VS pattern
        if rule.vs_pattern:
            vs = self._get_vs(transaction)
            if not vs or not re.match(rule.vs_pattern, vs, re.IGNORECASE):
                return False

        return True

    def _matches_vendor(self, transaction, rule: KnownTransaction) -> bool:
        """Check vendor-based match."""
        if not rule.vendor_pattern:
            return False

        pattern = re.compile(rule.vendor_pattern, re.IGNORECASE)
        text_to_match = f"{self._get_counter_name(transaction)} {self._get_note(transaction)}"

        return bool(pattern.search(text_to_match))

    def _matches_note(self, transaction, rule: KnownTransaction) -> bool:
        """Check note-based match using regex."""
        if not rule.note_pattern:
            return False

        try:
            pattern = re.compile(rule.note_pattern, re.IGNORECASE)
            note = self._get_note(transaction)

            if not pattern.search(note):
                return False

            # Optionally also check amount range
            amount = self._get_amount(transaction)
            if rule.amount_min is not None and abs(amount) < rule.amount_min:
                return False
            if rule.amount_max is not None and abs(amount) > rule.amount_max:
                return False

            return True
        except re.error:
            return False

    def _matches_account(self, transaction, rule: KnownTransaction) -> bool:
        """Check account/IBAN-based match."""
        if not rule.counter_account:
            return False

        # Exact match on counter_account (IBAN)
        return self._get_counter_account(transaction) == rule.counter_account
