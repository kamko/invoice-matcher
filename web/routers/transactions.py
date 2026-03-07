"""Router for transaction endpoints."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from web.database import get_db
from web.database.models import Transaction, Invoice, KnownTransaction
from web.schemas.transactions import (
    TransactionResponse,
    TransactionListResponse,
    TransactionSuggestionsResponse,
    InvoiceSuggestion,
    FetchTransactionsRequest,
    FetchTransactionsResponse,
    SkipTransactionRequest,
    MarkKnownRequest,
    UpdateTransactionRequest,
)
from web.services.matching_service import MatchingService
from web.routers.sse import send_progress, send_info, send_error, send_success
from parsers.fio_api import fetch_transactions_from_api

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


def _transaction_to_response(
    transaction: Transaction,
    db: Session
) -> TransactionResponse:
    """Convert Transaction model to response schema."""
    rule_reason = None
    if transaction.known_rule_id:
        rule = db.query(KnownTransaction).filter(
            KnownTransaction.id == transaction.known_rule_id
        ).first()
        if rule:
            rule_reason = rule.reason

    return TransactionResponse(
        id=transaction.id,
        date=transaction.date,
        amount=transaction.amount,
        currency=transaction.currency,
        counter_account=transaction.counter_account,
        counter_name=transaction.counter_name,
        vs=transaction.vs,
        note=transaction.note,
        type=transaction.type,
        raw_type=transaction.raw_type,
        status=transaction.status,
        known_rule_id=transaction.known_rule_id,
        skip_reason=transaction.skip_reason,
        fetched_at=transaction.fetched_at,
        rule_reason=rule_reason,
    )


@router.get("", response_model=TransactionListResponse)
def list_transactions(
    month: Optional[str] = Query(None, description="Filter by month (YYYY-MM)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    type: Optional[str] = Query(None, description="Filter by type (expense/income/fee)"),
    db: Session = Depends(get_db)
):
    """List transactions with optional filters."""
    query = db.query(Transaction)

    if month:
        # Filter by transaction date month
        year, mon = map(int, month.split('-'))
        from calendar import monthrange
        start_date = datetime(year, mon, 1).date()
        last_day = monthrange(year, mon)[1]
        end_date = datetime(year, mon, last_day).date()
        query = query.filter(
            Transaction.date >= start_date,
            Transaction.date <= end_date
        )

    if status:
        query = query.filter(Transaction.status == status)

    if type:
        query = query.filter(Transaction.type == type)

    transactions = query.order_by(Transaction.date.desc()).all()

    unmatched = sum(1 for t in transactions if t.status == 'unmatched')
    matched = sum(1 for t in transactions if t.status == 'matched')
    known = sum(1 for t in transactions if t.status == 'known')
    skipped = sum(1 for t in transactions if t.status == 'skipped')

    return TransactionListResponse(
        transactions=[_transaction_to_response(t, db) for t in transactions],
        total=len(transactions),
        unmatched=unmatched,
        matched=matched,
        known=known,
        skipped=skipped,
    )


@router.get("/{transaction_id}", response_model=TransactionResponse)
def get_transaction(transaction_id: str, db: Session = Depends(get_db)):
    """Get a single transaction by ID."""
    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return _transaction_to_response(transaction, db)


@router.patch("/{transaction_id}", response_model=TransactionResponse)
def update_transaction(
    transaction_id: str,
    request: UpdateTransactionRequest,
    db: Session = Depends(get_db)
):
    """Update a transaction's editable fields."""
    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Update only provided fields
    if request.counter_name is not None:
        transaction.counter_name = request.counter_name
    if request.note is not None:
        transaction.note = request.note
    if request.vs is not None:
        transaction.vs = request.vs
    if request.type is not None:
        if request.type not in ('expense', 'income', 'fee'):
            raise HTTPException(status_code=400, detail="Invalid type")
        transaction.type = request.type

    db.commit()
    db.refresh(transaction)

    return _transaction_to_response(transaction, db)


@router.post("/fetch", response_model=FetchTransactionsResponse)
def fetch_transactions(
    request: FetchTransactionsRequest,
    db: Session = Depends(get_db)
):
    """Fetch transactions from Fio Bank."""
    send_info("Connecting to Fio Bank API...", "fetch_transactions")

    try:
        raw_transactions = fetch_transactions_from_api(
            token=request.fio_token.strip(),
            from_date=request.from_date,
            to_date=request.to_date,
        )
    except Exception as e:
        send_error(f"Fio API error: {e}", "fetch_transactions")
        raise HTTPException(status_code=502, detail=f"Fio API error: {e}")

    fetched = len(raw_transactions)
    send_info(f"Fetched {fetched} transactions from bank", "fetch_transactions")

    new_count = 0
    existing_count = 0
    known_matched = 0

    matching = MatchingService(db)

    for i, raw in enumerate(raw_transactions):
        if i % 10 == 0:  # Update progress every 10 transactions
            send_progress("fetch_transactions", i, fetched, f"Processing transactions...")

        # Check if transaction already exists
        existing = db.query(Transaction).filter(
            Transaction.id == raw.id
        ).first()

        if existing:
            existing_count += 1
            continue

        # Classify transaction type
        trans_type = 'expense'
        if raw.is_fee:
            trans_type = 'fee'
        elif raw.amount > 0:
            trans_type = 'income'

        # Create new transaction
        transaction = Transaction(
            id=raw.id,
            date=raw.date,
            amount=raw.amount,
            currency=raw.currency,
            counter_account=raw.counter_account,
            counter_name=raw.counter_name,
            vs=raw.vs,
            note=raw.note,
            type=trans_type,
            raw_type=raw.raw_type,
            status='unmatched',
            fetched_at=datetime.utcnow(),
        )

        # Check known transaction rules
        rule = matching.apply_known_rules(transaction)
        if rule:
            transaction.status = 'known'
            transaction.known_rule_id = rule.id
            known_matched += 1

        db.add(transaction)
        new_count += 1

    db.commit()

    # Run auto-matching on invoices
    send_info("Running auto-matching...", "fetch_transactions")
    matching.run_auto_matching()

    send_success(f"Fetched {new_count} new transactions, {known_matched} matched by rules", "fetch_transactions")

    return FetchTransactionsResponse(
        fetched=fetched,
        new=new_count,
        existing=existing_count,
        known_matched=known_matched,
    )


@router.post("/{transaction_id}/skip", response_model=TransactionResponse)
def skip_transaction(
    transaction_id: str,
    request: SkipTransactionRequest,
    db: Session = Depends(get_db)
):
    """Mark a transaction as skipped."""
    matching = MatchingService(db)

    try:
        transaction = matching.skip_transaction(transaction_id, request.reason)
        return _transaction_to_response(transaction, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{transaction_id}/unskip", response_model=TransactionResponse)
def unskip_transaction(transaction_id: str, db: Session = Depends(get_db)):
    """Remove skip status from a transaction."""
    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if transaction.status != 'skipped':
        raise HTTPException(status_code=400, detail="Transaction is not skipped")

    transaction.status = 'unmatched'
    transaction.skip_reason = None
    db.commit()

    return _transaction_to_response(transaction, db)


@router.post("/{transaction_id}/mark-known")
def mark_transaction_known(
    transaction_id: str,
    request: MarkKnownRequest,
    db: Session = Depends(get_db)
):
    """Create a known transaction rule and apply it."""
    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Create the rule
    rule = KnownTransaction(
        rule_type=request.rule_type,
        reason=request.reason,
        vendor_pattern=request.vendor_pattern,
        note_pattern=request.note_pattern,
        amount=request.amount,
        amount_min=request.amount_min,
        amount_max=request.amount_max,
        counter_account=request.counter_account,
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    # Mark this transaction as known
    matching = MatchingService(db)
    matching.mark_transaction_known(transaction_id, rule.id)

    # Apply rule to other unmatched transactions
    matched_count = 0
    unmatched = db.query(Transaction).filter(
        Transaction.status == 'unmatched'
    ).all()

    for t in unmatched:
        if matching._matches_rule(t, rule):
            t.status = 'known'
            t.known_rule_id = rule.id
            matched_count += 1

    db.commit()

    return {
        "success": True,
        "rule_id": rule.id,
        "matched_count": matched_count + 1,  # +1 for original transaction
    }


@router.get("/{transaction_id}/suggestions", response_model=TransactionSuggestionsResponse)
def get_transaction_suggestions(transaction_id: str, db: Session = Depends(get_db)):
    """Get invoice suggestions for a transaction."""
    transaction = db.query(Transaction).filter(
        Transaction.id == transaction_id
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    matching = MatchingService(db)
    suggestions = matching.suggest_matches_for_transaction(transaction)

    return TransactionSuggestionsResponse(
        transaction_id=transaction_id,
        suggestions=[
            InvoiceSuggestion(
                invoice_id=inv.id,
                filename=inv.filename,
                vendor=inv.vendor,
                amount=inv.amount,
                invoice_date=inv.invoice_date,
                score=score,
            )
            for inv, score in suggestions
        ]
    )


@router.post("/{transaction_id}/match")
def match_transaction_to_invoice(
    transaction_id: str,
    invoice_id: int = Query(..., description="Invoice ID to match"),
    db: Session = Depends(get_db)
):
    """Match a transaction to an invoice."""
    matching = MatchingService(db)

    try:
        invoice, transaction = matching.match_invoice_to_transaction(
            invoice_id,
            transaction_id
        )
        return {
            "success": True,
            "invoice_id": invoice.id,
            "transaction_id": transaction.id,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
