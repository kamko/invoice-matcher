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
    """Create a new known transaction rule."""
    service = KnownTransactionService(db)
    return service.create(data)


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
