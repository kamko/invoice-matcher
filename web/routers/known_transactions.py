"""Router for known transaction rules."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from web.database import get_db
from web.schemas.known_transaction import (
    KnownTransactionCreate,
    KnownTransactionUpdate,
    KnownTransactionResponse,
)
from web.services.known_trans_service import KnownTransactionService

router = APIRouter(prefix="/api/known-transactions", tags=["known-transactions"])


@router.get("", response_model=List[KnownTransactionResponse])
def list_known_transactions(
    active_only: bool = False,
    db: Session = Depends(get_db)
):
    """Get all known transaction rules."""
    service = KnownTransactionService(db)
    return service.get_all(active_only=active_only)


@router.get("/{rule_id}", response_model=KnownTransactionResponse)
def get_known_transaction(rule_id: int, db: Session = Depends(get_db)):
    """Get a specific known transaction rule."""
    service = KnownTransactionService(db)
    rule = service.get_by_id(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


@router.post("", response_model=KnownTransactionResponse, status_code=201)
def create_known_transaction(
    data: KnownTransactionCreate,
    db: Session = Depends(get_db)
):
    """Create a new known transaction rule and apply to existing months."""
    service = KnownTransactionService(db)
    rule = service.create(data)

    # Apply new rule to all existing completed months
    apply_rule_to_existing_months(rule, db)

    return rule


def apply_rule_to_existing_months(rule, db: Session):
    """Apply a new rule to all completed months, moving matching transactions to known."""
    from web.database.models import MonthlyReconciliation
    from models.transaction import Transaction
    from decimal import Decimal
    from datetime import datetime

    service = KnownTransactionService(db)

    # Get all months with results (regardless of status)
    months = db.query(MonthlyReconciliation).filter(
        MonthlyReconciliation.results_json.isnot(None)
    ).all()

    for month in months:
        results = month.results_json
        if not results or "unmatched" not in results:
            continue

        unmatched = results.get("unmatched", [])
        known = results.get("known", [])
        newly_matched = []
        still_unmatched = []

        for t_data in unmatched:
            # Reconstruct transaction to test against rule
            try:
                t = Transaction(
                    id=t_data["id"],
                    date=datetime.strptime(t_data["date"], "%Y-%m-%d").date(),
                    amount=Decimal(t_data["amount"]),
                    currency=t_data["currency"],
                    counter_account=t_data.get("counter_account") or "",
                    counter_name=t_data.get("counter_name") or "",
                    vs=t_data.get("vs") or "",
                    note=t_data.get("note") or "",
                    transaction_type=t_data.get("transaction_type") or "wire",
                    raw_type=t_data.get("raw_type") or t_data.get("transaction_type") or "wire",
                )

                if service._matches_rule(t, rule):
                    # Move to known
                    newly_matched.append({
                        **t_data,
                        "rule_reason": rule.reason,
                    })
                else:
                    still_unmatched.append(t_data)
            except Exception:
                # Keep in unmatched if reconstruction fails
                still_unmatched.append(t_data)

        if newly_matched:
            # Update month results
            results["unmatched"] = still_unmatched
            results["known"] = known + newly_matched
            month.results_json = results
            month.unmatched_count = len(still_unmatched)
            month.known_count = len(results["known"])

    db.commit()


@router.put("/{rule_id}", response_model=KnownTransactionResponse)
def update_known_transaction(
    rule_id: int,
    data: KnownTransactionUpdate,
    db: Session = Depends(get_db)
):
    """Update a known transaction rule."""
    service = KnownTransactionService(db)
    rule = service.update(rule_id, data)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


@router.delete("/{rule_id}", status_code=204)
def delete_known_transaction(rule_id: int, db: Session = Depends(get_db)):
    """Delete a known transaction rule."""
    service = KnownTransactionService(db)
    if not service.delete(rule_id):
        raise HTTPException(status_code=404, detail="Rule not found")


@router.post("/reapply-all")
def reapply_all_rules(db: Session = Depends(get_db)):
    """Reapply all active rules to all months with existing results."""
    from web.database.models import MonthlyReconciliation
    from models.transaction import Transaction
    from decimal import Decimal
    from datetime import datetime

    service = KnownTransactionService(db)
    active_rules = service.get_all(active_only=True)

    if not active_rules:
        return {"success": True, "message": "No active rules", "months_updated": 0, "transactions_moved": 0}

    # Get all months with results
    months = db.query(MonthlyReconciliation).filter(
        MonthlyReconciliation.results_json.isnot(None)
    ).all()

    total_moved = 0
    months_updated = 0

    for month in months:
        results = month.results_json
        if not results or "unmatched" not in results:
            continue

        unmatched = results.get("unmatched", [])
        known = results.get("known", [])
        newly_matched = []
        still_unmatched = []

        for t_data in unmatched:
            try:
                t = Transaction(
                    id=t_data["id"],
                    date=datetime.strptime(t_data["date"], "%Y-%m-%d").date(),
                    amount=Decimal(t_data["amount"]),
                    currency=t_data["currency"],
                    counter_account=t_data.get("counter_account") or "",
                    counter_name=t_data.get("counter_name") or "",
                    vs=t_data.get("vs") or "",
                    note=t_data.get("note") or "",
                    transaction_type=t_data.get("transaction_type") or "wire",
                    raw_type=t_data.get("raw_type") or t_data.get("transaction_type") or "wire",
                )

                # Check against all active rules
                matched_rule = None
                for rule in active_rules:
                    if service._matches_rule(t, rule):
                        matched_rule = rule
                        break

                if matched_rule:
                    newly_matched.append({
                        **t_data,
                        "rule_reason": matched_rule.reason,
                    })
                else:
                    still_unmatched.append(t_data)
            except Exception:
                still_unmatched.append(t_data)

        if newly_matched:
            results["unmatched"] = still_unmatched
            results["known"] = known + newly_matched
            month.results_json = results
            month.unmatched_count = len(still_unmatched)
            month.known_count = len(results["known"])
            total_moved += len(newly_matched)
            months_updated += 1

    db.commit()

    return {
        "success": True,
        "months_updated": months_updated,
        "transactions_moved": total_moved,
    }
