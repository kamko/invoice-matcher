"""Router for known transaction rules."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from web.auth import get_current_user
from web.database import get_db
from web.database.models import Transaction, User
from web.schemas.known_transaction import (
    KnownTransactionCreate,
    KnownTransactionUpdate,
    KnownTransactionResponse,
)
from web.services.known_trans_service import KnownTransactionService
from web.services.matching_service import MatchingService

router = APIRouter(prefix="/api/known-transactions", tags=["known-transactions"])


@router.get("", response_model=List[KnownTransactionResponse])
def list_known_transactions(
    active_only: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all known transaction rules."""
    service = KnownTransactionService(db, user.id)
    return service.get_all(active_only=active_only)


@router.get("/{rule_id}", response_model=KnownTransactionResponse)
def get_known_transaction(
    rule_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific known transaction rule."""
    service = KnownTransactionService(db, user.id)
    rule = service.get_by_id(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


@router.post("", response_model=KnownTransactionResponse, status_code=201)
def create_known_transaction(
    data: KnownTransactionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new known transaction rule and apply to existing transactions."""
    service = KnownTransactionService(db, user.id)
    rule = service.create(data)

    # Apply new rule to all existing unmatched transactions
    matching_service = MatchingService(db, user.id)
    unmatched = db.query(Transaction).filter(
        Transaction.status == 'unmatched',
        Transaction.user_id == user.id,
    ).all()

    for t in unmatched:
        if matching_service._matches_rule(t, rule):
            t.status = 'known'
            t.known_rule_id = rule.id

    db.commit()

    return rule


@router.put("/{rule_id}", response_model=KnownTransactionResponse)
def update_known_transaction(
    rule_id: int,
    data: KnownTransactionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a known transaction rule."""
    service = KnownTransactionService(db, user.id)
    rule = service.update(rule_id, data)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


@router.delete("/{rule_id}", status_code=204)
def delete_known_transaction(
    rule_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a known transaction rule."""
    service = KnownTransactionService(db, user.id)
    if not service.delete(rule_id):
        raise HTTPException(status_code=404, detail="Rule not found")


@router.post("/reapply-all")
def reapply_all_rules(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reapply all active rules to all unmatched transactions."""
    service = KnownTransactionService(db, user.id)
    matching_service = MatchingService(db, user.id)
    active_rules = service.get_all(active_only=True)

    if not active_rules:
        return {"success": True, "message": "No active rules", "transactions_updated": 0}

    # Get all unmatched transactions
    unmatched = db.query(Transaction).filter(
        Transaction.status == 'unmatched',
        Transaction.user_id == user.id,
    ).all()

    total_updated = 0

    for t in unmatched:
        for rule in active_rules:
            if matching_service._matches_rule(t, rule):
                t.status = 'known'
                t.known_rule_id = rule.id
                total_updated += 1
                break

    db.commit()

    return {
        "success": True,
        "transactions_updated": total_updated,
    }
