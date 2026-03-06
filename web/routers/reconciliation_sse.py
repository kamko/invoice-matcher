"""SSE-based reconciliation for real-time progress updates."""

import asyncio
import json
import re
from pathlib import Path
from typing import AsyncGenerator
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from web.database import get_db
from web.database.models import ReconciliationSession, InvoicePayment
from web.services.known_trans_service import KnownTransactionService
from web.routers.gdrive import _gdrive_service
from web.config import DATA_DIR

from models.transaction import Transaction
from parsers.fio_api import fetch_transactions_from_api
from parsers.pdf_parser import parse_invoices
from matching.matcher import Matcher

router = APIRouter(prefix="/api", tags=["reconciliation-sse"])


def sanitize_error(error: Exception) -> str:
    """Sanitize error message to remove sensitive data like API tokens in URLs."""
    msg = str(error)
    # Remove Fio API URLs that contain tokens
    # Pattern: https://www.fio.cz/ib_api/rest/...token.../...
    msg = re.sub(
        r'https?://[^\s]*fio[^\s]*',
        '[Fio API URL redacted]',
        msg,
        flags=re.IGNORECASE
    )
    # Also redact any URL with "token" in it
    msg = re.sub(
        r'https?://[^\s]*token[^\s]*',
        '[URL with token redacted]',
        msg,
        flags=re.IGNORECASE
    )
    return msg


class ReconcileSSERequest(BaseModel):
    from_date: str
    to_date: str
    fio_token: str
    gdrive_folder_id: str | None = None
    invoice_dir: str | None = None


def send_event(event: str, data: dict) -> str:
    """Format a Server-Sent Event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/reconcile-stream")
async def reconcile_stream(
    request: ReconcileSSERequest,
    db: Session = Depends(get_db)
):
    """Stream reconciliation progress via SSE."""

    async def generate() -> AsyncGenerator[str, None]:
        try:
            # Parse dates
            from_date = datetime.strptime(request.from_date, "%Y-%m-%d").date()
            to_date = datetime.strptime(request.to_date, "%Y-%m-%d").date()

            # Create session
            session = ReconciliationSession(
                from_date=datetime.combine(from_date, datetime.min.time()),
                to_date=datetime.combine(to_date, datetime.min.time()),
                gdrive_folder_id=request.gdrive_folder_id,
                status="processing"
            )
            db.add(session)
            db.commit()
            db.refresh(session)

            yield send_event("session", {"session_id": session.id})
            yield send_event("progress", {"step": "started", "message": "Starting reconciliation..."})
            await asyncio.sleep(0.1)

            # Step 1: Fetch transactions
            yield send_event("progress", {"step": "fetching", "message": "Fetching transactions from Fio Bank..."})
            await asyncio.sleep(0.1)

            try:
                transactions = await asyncio.to_thread(
                    fetch_transactions_from_api,
                    request.fio_token.strip(),
                    from_date,
                    to_date
                )
                yield send_event("progress", {
                    "step": "fetched",
                    "message": f"Found {len(transactions)} transactions",
                    "count": len(transactions)
                })
            except Exception as e:
                error_msg = sanitize_error(e)
                yield send_event("error", {"message": f"Failed to fetch transactions: {error_msg}"})
                session.status = "failed"
                session.error_message = error_msg
                db.commit()
                return

            await asyncio.sleep(0.1)

            # Step 2: Get invoices
            invoice_dir = None
            invoices = []

            if request.gdrive_folder_id:
                yield send_event("progress", {"step": "downloading", "message": "Downloading invoices from Google Drive..."})
                await asyncio.sleep(0.1)

                if _gdrive_service._credentials:
                    try:
                        invoice_dir, files, _ = await asyncio.to_thread(
                            _gdrive_service.download_pdfs,
                            request.gdrive_folder_id,
                            db,
                            True  # force_refresh for sync
                        )
                        yield send_event("progress", {
                            "step": "downloaded",
                            "message": f"Downloaded {len(files)} PDF files",
                            "count": len(files)
                        })
                    except Exception as e:
                        error_msg = sanitize_error(e)
                        yield send_event("error", {"message": f"Failed to download: {error_msg}"})
                        session.status = "failed"
                        session.error_message = error_msg
                        db.commit()
                        return
                else:
                    yield send_event("error", {"message": "Not authenticated with Google Drive"})
                    session.status = "failed"
                    session.error_message = "Not authenticated with Google Drive"
                    db.commit()
                    return

            elif request.invoice_dir:
                invoice_dir = Path(request.invoice_dir)
                if not invoice_dir.exists():
                    yield send_event("error", {"message": f"Directory not found: {request.invoice_dir}"})
                    session.status = "failed"
                    session.error_message = f"Directory not found: {request.invoice_dir}"
                    db.commit()
                    return

            await asyncio.sleep(0.1)

            # Step 3: Parse invoices
            if invoice_dir:
                yield send_event("progress", {"step": "parsing", "message": "Parsing invoice PDFs..."})
                await asyncio.sleep(0.1)

                invoices = await asyncio.to_thread(parse_invoices, invoice_dir)
                yield send_event("progress", {
                    "step": "parsed",
                    "message": f"Parsed {len(invoices)} invoices",
                    "count": len(invoices)
                })

            await asyncio.sleep(0.1)

            # Step 4: Check known transactions
            yield send_event("progress", {"step": "checking_known", "message": "Checking known transaction rules..."})
            await asyncio.sleep(0.1)

            known_service = KnownTransactionService(db)
            known_transactions = []
            unknown_transactions = []
            fee_transactions = []
            income_transactions = []

            for trans in transactions:
                if trans.is_fee:
                    fee_transactions.append(trans)
                    continue
                # Separate income (positive amounts) from expenses
                if trans.amount > 0:
                    income_transactions.append(trans)
                    continue
                rule = known_service.match_transaction(trans)
                if rule:
                    known_transactions.append((trans, rule))
                    known_service.record_match(rule, trans, session.id)
                else:
                    unknown_transactions.append(trans)

            yield send_event("progress", {
                "step": "known_checked",
                "message": f"Found {len(known_transactions)} known, {len(fee_transactions)} fees, {len(income_transactions)} income",
                "known_count": len(known_transactions),
                "unknown_count": len(unknown_transactions),
                "fee_count": len(fee_transactions),
                "income_count": len(income_transactions)
            })

            await asyncio.sleep(0.1)

            # Step 5: Match transactions with invoices
            yield send_event("progress", {"step": "matching", "message": "Matching transactions with invoices..."})
            await asyncio.sleep(0.1)

            matcher = Matcher()
            matched, unmatched_trans, unmatched_inv = matcher.match_all(unknown_transactions, invoices)

            yield send_event("progress", {
                "step": "matched",
                "message": f"Matched {len(matched)} transactions",
                "matched_count": len(matched),
                "unmatched_count": len(unmatched_trans)
            })

            await asyncio.sleep(0.1)

            # Step 6: Save results
            yield send_event("progress", {"step": "saving", "message": "Saving results..."})

            # Serialize results
            results = {
                "matched": [
                    {
                        "transaction": serialize_transaction(m.transaction),
                        "invoice": serialize_invoice(m.invoice) if m.invoice else None,
                        "confidence": m.confidence,
                        "confidence_pct": m.confidence_pct,
                        "status": m.status,
                        "strategy_scores": m.strategy_scores,
                    }
                    for m in matched
                ],
                "unmatched": [serialize_transaction(t) for t in unmatched_trans],
                "unmatched_invoices": [serialize_invoice(inv) for inv in unmatched_inv],
                "known": [
                    {
                        **serialize_transaction(t),
                        "rule_reason": rule.reason,
                                            }
                    for t, rule in known_transactions
                ],
                "fees": [serialize_transaction(t) for t in fee_transactions],
                "income": [serialize_transaction(t) for t in income_transactions],
            }

            session.results_json = results
            session.matched_count = len([m for m in matched if m.status == "OK"])
            session.review_count = len([m for m in matched if m.status == "REVIEW"])
            session.unmatched_count = len(unmatched_trans)
            session.known_count = len(known_transactions)
            session.status = "completed"
            session.completed_at = datetime.utcnow()
            db.commit()

            yield send_event("complete", {
                "session_id": session.id,
                "matched_count": session.matched_count,
                "review_count": session.review_count,
                "unmatched_count": session.unmatched_count,
                "known_count": session.known_count,
                "fee_count": len(fee_transactions),
                "income_count": len(income_transactions)
            })

        except Exception as e:
            yield send_event("error", {"message": sanitize_error(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


def serialize_transaction(t: Transaction) -> dict:
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


def serialize_invoice(inv) -> dict:
    return {
        "file_path": str(inv.file_path),
        "filename": inv.filename,
        "invoice_date": str(inv.invoice_date),
        "invoice_number": inv.invoice_number,
        "payment_type": inv.payment_type,
        "vendor": inv.vendor,
        "amount": str(inv.amount) if inv.amount else None,
        "vs": inv.vs,
        "gdrive_file_id": inv.gdrive_file_id,
        "is_credit_note": inv.is_credit_note,
        "is_cash": inv.is_cash,
        "receipt_index": inv.receipt_index,
    }


# ===== Monthly SSE Endpoint =====

class MonthlyReconcileSSERequest(BaseModel):
    year_month: str
    fio_token: str
    gdrive_folder_id: str | None = None
    prev_month_gdrive_folder_id: str | None = None
    invoice_dir: str | None = None


class BatchSyncRequest(BaseModel):
    """Request to sync multiple months at once."""
    months: list[str]  # List of year-month strings, e.g., ["2026-01", "2026-02", "2026-03"]
    fio_token: str


@router.post("/months/{year_month}/sync-stream")
async def monthly_reconcile_stream(
    year_month: str,
    request: MonthlyReconcileSSERequest,
    db: Session = Depends(get_db)
):
    """Stream monthly reconciliation progress via SSE."""
    from calendar import monthrange
    from web.database.models import MonthlyReconciliation, AppSettings

    async def generate() -> AsyncGenerator[str, None]:
        try:
            # Parse year-month to get date range
            year, mon = map(int, year_month.split("-"))
            from_date = datetime(year, mon, 1).date()
            last_day = monthrange(year, mon)[1]
            end_of_month = datetime(year, mon, last_day).date()
            # Use today if it's the current month, otherwise use end of month
            today = datetime.now().date()
            to_date = min(end_of_month, today) if today >= from_date else end_of_month

            # Auto-resolve folder from parent folder setting
            folder_id = request.gdrive_folder_id
            folder_name = None

            if not folder_id and _gdrive_service._credentials:
                # Check for parent folder setting
                parent_setting = db.query(AppSettings).filter(
                    AppSettings.key == "invoice_parent_folder_id"
                ).first()

                if parent_setting and parent_setting.value:
                    # Look for YYYYMM subfolder
                    subfolder_name = f"{year}{mon:02d}"
                    subfolder = _gdrive_service.find_subfolder(parent_setting.value, subfolder_name)
                    if subfolder:
                        folder_id = subfolder.id
                        folder_name = subfolder.name

            # Get or create month record
            month = db.query(MonthlyReconciliation).filter(
                MonthlyReconciliation.year_month == year_month
            ).first()

            if not month:
                month = MonthlyReconciliation(
                    year_month=year_month,
                    gdrive_folder_id=folder_id,
                    gdrive_folder_name=folder_name,
                    status="processing"
                )
                db.add(month)
                db.commit()
                db.refresh(month)
            else:
                month.status = "processing"
                if folder_id:
                    month.gdrive_folder_id = folder_id
                if folder_name:
                    month.gdrive_folder_name = folder_name
                db.commit()

            yield send_event("started", {"year_month": year_month})
            yield send_event("progress", {"step": "started", "message": f"Starting reconciliation for {year_month}..."})
            await asyncio.sleep(0.1)

            # Step 1: Fetch transactions (use cache for past months)
            is_past_month = to_date < today
            use_cache = is_past_month and month.transactions_json is not None

            if use_cache:
                # Use cached transactions for past months
                yield send_event("progress", {"step": "fetching", "message": "Using cached transactions (past month)..."})
                await asyncio.sleep(0.1)

                # Reconstruct Transaction objects from cache
                cached_data = month.transactions_json
                transactions = []
                for t_data in cached_data:
                    from decimal import Decimal
                    t = Transaction(
                        id=t_data["id"],
                        date=datetime.strptime(t_data["date"], "%Y-%m-%d").date(),
                        amount=Decimal(t_data["amount"]),
                        currency=t_data["currency"],
                        counter_account=t_data.get("counter_account") or "",
                        counter_name=t_data.get("counter_name") or "",
                        vs=t_data.get("vs") or "",
                        note=t_data.get("note") or "",
                        transaction_type=t_data.get("transaction_type", "wire"),
                        raw_type=t_data.get("raw_type", t_data.get("transaction_type", "wire")),
                    )
                    transactions.append(t)

                yield send_event("progress", {
                    "step": "fetched",
                    "message": f"Loaded {len(transactions)} cached transactions",
                    "count": len(transactions)
                })
            else:
                # Fetch from Fio API
                yield send_event("progress", {"step": "fetching", "message": "Fetching transactions from Fio Bank..."})
                await asyncio.sleep(0.1)

                try:
                    transactions = await asyncio.to_thread(
                        fetch_transactions_from_api,
                        request.fio_token.strip(),
                        from_date,
                        to_date
                    )
                    yield send_event("progress", {
                        "step": "fetched",
                        "message": f"Found {len(transactions)} transactions",
                        "count": len(transactions)
                    })

                    # Cache transactions for future syncs (only for past months)
                    if is_past_month:
                        month.transactions_json = [
                            {
                                "id": t.id,
                                "date": str(t.date),
                                "amount": str(t.amount),
                                "currency": t.currency,
                                "counter_account": t.counter_account or "",
                                "counter_name": t.counter_name or "",
                                "vs": t.vs or "",
                                "note": t.note or "",
                                "transaction_type": t.transaction_type,
                                "raw_type": t.raw_type,
                            }
                            for t in transactions
                        ]
                except Exception as e:
                    error_msg = sanitize_error(e)
                    yield send_event("error", {"message": f"Failed to fetch transactions: {error_msg}"})
                    month.status = "failed"
                    month.error_message = error_msg
                    db.commit()
                    return

            await asyncio.sleep(0.1)

            # Step 2: Get invoices from current month folder
            invoices = []
            file_id_map = {}  # filename -> gdrive file id
            invoice_source_month = {}  # gdrive_file_id -> source month (for tracking)

            # Helper to calculate previous month
            def get_prev_month(ym: str) -> str:
                y, m = map(int, ym.split("-"))
                prev_date = datetime(y, m, 1) - __import__('datetime').timedelta(days=1)
                return f"{prev_date.year}-{prev_date.month:02d}"

            prev_month = get_prev_month(year_month)

            # Auto-resolve previous month folder from parent folder setting
            prev_month_folder_id = request.prev_month_gdrive_folder_id
            if not prev_month_folder_id and _gdrive_service._credentials:
                parent_setting = db.query(AppSettings).filter(
                    AppSettings.key == "invoice_parent_folder_id"
                ).first()
                if parent_setting and parent_setting.value:
                    prev_y, prev_m = map(int, prev_month.split("-"))
                    prev_subfolder_name = f"{prev_y}{prev_m:02d}"
                    prev_subfolder = _gdrive_service.find_subfolder(parent_setting.value, prev_subfolder_name)
                    if prev_subfolder:
                        prev_month_folder_id = prev_subfolder.id

            # Use resolved folder_id (from earlier auto-resolution or request)
            current_folder_id = folder_id or month.gdrive_folder_id

            if current_folder_id:
                yield send_event("progress", {"step": "downloading", "message": "Downloading invoices from Google Drive..."})
                await asyncio.sleep(0.1)

                if _gdrive_service._credentials:
                    try:
                        invoice_dir, files, curr_file_id_map = await asyncio.to_thread(
                            _gdrive_service.download_pdfs,
                            current_folder_id,
                            db,
                            True  # force_refresh for sync
                        )
                        file_id_map.update(curr_file_id_map)
                        yield send_event("progress", {
                            "step": "downloaded",
                            "message": f"Downloaded {len(files)} PDF files",
                            "count": len(files)
                        })

                        # Parse current month invoices
                        if invoice_dir:
                            curr_invoices = await asyncio.to_thread(parse_invoices, invoice_dir)
                            # Set gdrive_file_id and source month on each invoice
                            for inv in curr_invoices:
                                inv.gdrive_file_id = file_id_map.get(inv.filename)
                                inv.source_month = year_month  # Track which folder this came from
                                if inv.gdrive_file_id:
                                    invoice_source_month[inv.gdrive_file_id] = year_month
                            invoices.extend(curr_invoices)
                    except Exception as e:
                        yield send_event("progress", {"step": "download_warning", "message": f"Warning: {sanitize_error(e)}"})
                else:
                    yield send_event("error", {"message": "Not authenticated with Google Drive"})
                    month.status = "failed"
                    month.error_message = "Not authenticated with Google Drive"
                    db.commit()
                    return

            # Step 2b: Get invoices from previous month folder (for late payments)
            if prev_month_folder_id:
                yield send_event("progress", {"step": "downloading_prev", "message": "Downloading previous month invoices..."})
                await asyncio.sleep(0.1)

                if _gdrive_service._credentials:
                    try:
                        prev_invoice_dir, prev_files, prev_file_id_map = await asyncio.to_thread(
                            _gdrive_service.download_pdfs,
                            prev_month_folder_id,
                            db,
                            True  # force_refresh for sync
                        )
                        file_id_map.update(prev_file_id_map)
                        if prev_invoice_dir:
                            prev_invoices = await asyncio.to_thread(parse_invoices, prev_invoice_dir)
                            # Set gdrive_file_id and source month on each invoice
                            for inv in prev_invoices:
                                inv.gdrive_file_id = file_id_map.get(inv.filename)
                                inv.source_month = prev_month  # Track which folder this came from
                                if inv.gdrive_file_id:
                                    invoice_source_month[inv.gdrive_file_id] = prev_month
                            invoices.extend(prev_invoices)
                            yield send_event("progress", {
                                "step": "downloaded_prev",
                                "message": f"Added {len(prev_invoices)} invoices from previous month",
                                "count": len(prev_invoices)
                            })
                    except Exception:
                        pass  # Silently ignore previous month errors

            await asyncio.sleep(0.1)

            yield send_event("progress", {
                "step": "parsed",
                "message": f"Total {len(invoices)} invoices to match",
                "count": len(invoices)
            })

            # Step 3: Check known transactions
            yield send_event("progress", {"step": "checking_known", "message": "Checking known transaction rules..."})
            await asyncio.sleep(0.1)

            known_service = KnownTransactionService(db)
            known_transactions = []
            unknown_transactions = []
            fee_transactions = []
            income_transactions = []

            for trans in transactions:
                if trans.is_fee:
                    fee_transactions.append(trans)
                    continue
                if trans.amount > 0:
                    income_transactions.append(trans)
                    continue
                rule = known_service.match_transaction(trans)
                if rule:
                    known_transactions.append((trans, rule))
                else:
                    unknown_transactions.append(trans)

            yield send_event("progress", {
                "step": "known_checked",
                "message": f"Found {len(known_transactions)} known, {len(fee_transactions)} fees, {len(income_transactions)} income",
                "known_count": len(known_transactions),
                "fee_count": len(fee_transactions),
                "income_count": len(income_transactions)
            })

            await asyncio.sleep(0.1)

            # Step 4: Match transactions with invoices
            # Separate invoices by type: cash (auto-paid), credit-notes, regular
            cash_invoices = [inv for inv in invoices if inv.is_cash]
            credit_note_invoices = [inv for inv in invoices if inv.is_credit_note and not inv.is_cash]
            regular_invoices = [inv for inv in invoices if not inv.is_credit_note and not inv.is_cash]

            yield send_event("progress", {"step": "matching", "message": "Matching transactions with invoices..."})
            await asyncio.sleep(0.1)

            matcher = Matcher()

            # Match regular invoices with expense transactions (negative amounts)
            matched, unmatched_trans, unmatched_regular_inv = matcher.match_all(unknown_transactions, regular_invoices)

            # Match credit-note invoices with income transactions (positive amounts)
            credit_matched, unmatched_income, unmatched_credit_inv = matcher.match_all(income_transactions, credit_note_invoices)

            # Cash invoices are auto-matched (paid with cash, no bank transaction needed)
            # We'll add them to matched results with a special "cash" indicator
            from matching.matcher import MatchResult
            cash_matched = [
                MatchResult(
                    transaction=None,  # No transaction for cash payments
                    invoice=inv,
                    confidence=1.0,
                    strategy_scores={"CashPayment": 1.0}
                )
                for inv in cash_invoices
            ]

            # Combine results
            all_matched = matched + credit_matched
            all_unmatched_inv = unmatched_regular_inv + unmatched_credit_inv
            # Cash invoices are handled separately in results

            yield send_event("progress", {
                "step": "matched",
                "message": f"Matched {len(all_matched)} transactions, {len(cash_invoices)} cash, {len(credit_matched)} credit notes",
                "matched_count": len(all_matched),
                "unmatched_count": len(unmatched_trans),
                "cash_count": len(cash_invoices),
                "credit_note_matched": len(credit_matched)
            })

            await asyncio.sleep(0.1)

            # Step 5: Save results
            yield send_event("progress", {"step": "saving", "message": "Saving results..."})

            # Build matched results - include both transaction matches and cash invoices
            matched_results = [
                {
                    "transaction": serialize_transaction(m.transaction),
                    "invoice": serialize_invoice(m.invoice) if m.invoice else None,
                    "confidence": m.confidence,
                    "confidence_pct": m.confidence_pct,
                    "status": m.status,
                    "strategy_scores": m.strategy_scores,
                }
                for m in all_matched
            ]
            # Add cash invoices as matched (no transaction needed)
            for inv in cash_invoices:
                matched_results.append({
                    "transaction": None,  # No bank transaction for cash
                    "invoice": serialize_invoice(inv),
                    "confidence": 1.0,
                    "confidence_pct": 100,
                    "status": "OK",
                    "strategy_scores": {"CashPayment": 1.0},
                })

            results = {
                "matched": matched_results,
                "unmatched": [serialize_transaction(t) for t in unmatched_trans],
                "unmatched_invoices": [serialize_invoice(inv) for inv in all_unmatched_inv],
                "known": [
                    {
                        **serialize_transaction(t),
                        "rule_reason": rule.reason,
                                            }
                    for t, rule in known_transactions
                ],
                "fees": [serialize_transaction(t) for t in fee_transactions],
                "income": [serialize_transaction(t) for t in unmatched_income],  # Only unmatched income now
            }

            month.results_json = results
            # Count includes both transaction matches and cash invoices
            month.matched_count = len([m for m in all_matched if m.status == "OK"]) + len(cash_invoices)
            month.review_count = len([m for m in all_matched if m.status == "REVIEW"])
            month.unmatched_count = len(unmatched_trans)
            month.known_count = len(known_transactions)
            month.fee_count = len(fee_transactions)
            month.income_count = len(unmatched_income)  # Only unmatched income
            month.status = "completed"
            month.last_synced_at = datetime.utcnow()
            month.error_message = None

            # Track invoice payments for cross-month reporting
            from decimal import Decimal

            # Clear records for invoices from THIS month's folder only
            # (we'll recreate them based on current matches)
            # BUT preserve manually uploaded invoices - they shouldn't be deleted by sync
            if request.gdrive_folder_id:
                db.query(InvoicePayment).filter(
                    InvoicePayment.invoice_month == year_month,
                    InvoicePayment.is_manual_upload == False  # Preserve manual uploads
                ).delete()

            # Record matched invoices with their payment info (includes credit notes)
            for m in all_matched:
                if m.invoice and m.invoice.gdrive_file_id:
                    source_month = getattr(m.invoice, 'source_month', year_month)

                    if source_month == year_month:
                        # Invoice is from current month folder - create new record
                        payment = InvoicePayment(
                            invoice_month=source_month,
                            gdrive_file_id=m.invoice.gdrive_file_id,
                            filename=m.invoice.filename,
                            receipt_index=m.invoice.receipt_index,
                            paid_month=year_month,
                            transaction_id=m.transaction.id,
                            amount=Decimal(str(m.invoice.amount)) if m.invoice.amount else None,
                            vendor=m.invoice.vendor,
                        )
                        db.add(payment)
                    else:
                        # Invoice is from previous month folder - update existing record
                        existing = db.query(InvoicePayment).filter(
                            InvoicePayment.gdrive_file_id == m.invoice.gdrive_file_id,
                            InvoicePayment.receipt_index == m.invoice.receipt_index
                        ).first()
                        if existing:
                            existing.paid_month = year_month
                            existing.transaction_id = m.transaction.id
                            # Keep original invoice amount, don't overwrite with transaction amount
                        else:
                            # No existing record (prev month not synced yet), create one
                            payment = InvoicePayment(
                                invoice_month=source_month,
                                gdrive_file_id=m.invoice.gdrive_file_id,
                                filename=m.invoice.filename,
                                receipt_index=m.invoice.receipt_index,
                                paid_month=year_month,
                                transaction_id=m.transaction.id,
                                amount=Decimal(str(m.invoice.amount)) if m.invoice.amount else None,
                                vendor=m.invoice.vendor,
                            )
                            db.add(payment)

            # Record cash invoices as paid (no transaction needed)
            for inv in cash_invoices:
                if inv.gdrive_file_id:
                    source_month = getattr(inv, 'source_month', year_month)
                    if source_month == year_month:
                        payment = InvoicePayment(
                            invoice_month=source_month,
                            gdrive_file_id=inv.gdrive_file_id,
                            filename=inv.filename,
                            receipt_index=inv.receipt_index,
                            paid_month=year_month,  # Cash = paid immediately
                            transaction_id="CASH",  # Special marker for cash payments
                            amount=Decimal(str(inv.amount)) if inv.amount else None,
                            vendor=inv.vendor,
                        )
                        db.add(payment)

            # Record unmatched invoices from this month's folder
            # Regular invoices: unpaid; Credit notes: pending (needs income match)
            for inv in all_unmatched_inv:
                if inv.gdrive_file_id:
                    source_month = getattr(inv, 'source_month', year_month)
                    # Only record if it's from the current month folder
                    if source_month == year_month:
                        payment = InvoicePayment(
                            invoice_month=year_month,
                            gdrive_file_id=inv.gdrive_file_id,
                            filename=inv.filename,
                            receipt_index=inv.receipt_index,
                            paid_month=None,  # Not paid/credited yet
                            transaction_id=None,
                            amount=Decimal(str(inv.amount)) if inv.amount else None,
                            vendor=inv.vendor,
                        )
                        db.add(payment)

            db.commit()

            # Clean up downloaded files
            import shutil
            if current_folder_id:
                download_dir = _gdrive_service._download_dir / current_folder_id
                if download_dir.exists():
                    shutil.rmtree(download_dir, ignore_errors=True)
            if prev_month_folder_id:
                prev_download_dir = _gdrive_service._download_dir / prev_month_folder_id
                if prev_download_dir.exists():
                    shutil.rmtree(prev_download_dir, ignore_errors=True)

            yield send_event("complete", {
                "year_month": year_month,
                "matched_count": month.matched_count,
                "review_count": month.review_count,
                "unmatched_count": month.unmatched_count,
                "known_count": month.known_count,
                "fee_count": month.fee_count,
                "income_count": month.income_count
            })

        except Exception as e:
            # Reset month status on failure
            try:
                if 'month' in locals() and month:
                    month.status = "failed"
                    month.error_message = sanitize_error(e)
                    db.commit()
            except Exception:
                pass
            yield send_event("error", {"message": sanitize_error(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


# ===== Batch Sync Endpoint =====

@router.post("/batch-sync-stream")
async def batch_sync_stream(
    request: BatchSyncRequest,
    db: Session = Depends(get_db)
):
    """Sync multiple months efficiently with a single Fio API call."""
    from calendar import monthrange
    from web.database.models import MonthlyReconciliation, AppSettings

    async def generate() -> AsyncGenerator[str, None]:
        try:
            if not request.months:
                yield send_event("error", {"message": "No months specified"})
                return

            # Sort months chronologically
            sorted_months = sorted(request.months)
            first_month = sorted_months[0]
            last_month = sorted_months[-1]

            yield send_event("started", {"months": sorted_months})
            yield send_event("progress", {"step": "started", "message": f"Batch sync for {len(sorted_months)} months..."})
            await asyncio.sleep(0.1)

            # Step 1: Load cached transactions and determine what needs fetching
            yield send_event("progress", {"step": "checking_cache", "message": "Checking cached transactions..."})
            await asyncio.sleep(0.1)

            today = datetime.now().date()
            transactions_by_month: dict[str, list] = {}
            months_to_fetch: list[str] = []

            # Check each month for cached transactions
            for ym in sorted_months:
                y, m = map(int, ym.split("-"))
                month_end = datetime(y, m, monthrange(y, m)[1]).date()
                is_past_month = month_end < today

                # Try to load from cache
                month_record = db.query(MonthlyReconciliation).filter(
                    MonthlyReconciliation.year_month == ym
                ).first()

                if month_record and month_record.transactions_json and is_past_month:
                    # Use cached transactions for past months
                    from decimal import Decimal
                    cached_trans = []
                    for t_data in month_record.transactions_json:
                        t = Transaction(
                            id=t_data["id"],
                            date=datetime.strptime(t_data["date"], "%Y-%m-%d").date(),
                            amount=Decimal(t_data["amount"]),
                            currency=t_data["currency"],
                            counter_account=t_data.get("counter_account") or "",
                            counter_name=t_data.get("counter_name") or "",
                            vs=t_data.get("vs") or "",
                            note=t_data.get("note") or "",
                            transaction_type=t_data.get("transaction_type", "wire"),
                            raw_type=t_data.get("raw_type", t_data.get("transaction_type", "wire")),
                        )
                        cached_trans.append(t)
                    transactions_by_month[ym] = cached_trans
                else:
                    # Need to fetch this month
                    months_to_fetch.append(ym)

            cached_count = len(sorted_months) - len(months_to_fetch)
            if cached_count > 0:
                yield send_event("progress", {
                    "step": "cache_loaded",
                    "message": f"Loaded {cached_count} months from cache",
                    "cached_months": cached_count
                })

            # Fetch only the months we need from Fio API
            if months_to_fetch:
                # Calculate minimal date range for uncached months
                fetch_first = months_to_fetch[0]
                fetch_last = months_to_fetch[-1]
                first_year, first_mon = map(int, fetch_first.split("-"))
                last_year, last_mon = map(int, fetch_last.split("-"))

                from_date = datetime(first_year, first_mon, 1).date()
                last_day = monthrange(last_year, last_mon)[1]
                end_of_last_month = datetime(last_year, last_mon, last_day).date()
                to_date = min(end_of_last_month, today)

                yield send_event("progress", {"step": "fetching", "message": f"Fetching transactions {fetch_first} to {fetch_last}..."})
                await asyncio.sleep(0.1)

                try:
                    fetched_transactions = await asyncio.to_thread(
                        fetch_transactions_from_api,
                        request.fio_token.strip(),
                        from_date,
                        to_date
                    )
                    yield send_event("progress", {
                        "step": "fetched",
                        "message": f"Found {len(fetched_transactions)} transactions from API",
                        "count": len(fetched_transactions)
                    })

                    # Group fetched transactions by month
                    for t in fetched_transactions:
                        t_month = f"{t.date.year}-{t.date.month:02d}"
                        if t_month in months_to_fetch:
                            if t_month not in transactions_by_month:
                                transactions_by_month[t_month] = []
                            transactions_by_month[t_month].append(t)

                except Exception as e:
                    error_msg = sanitize_error(e)
                    yield send_event("error", {"message": f"Failed to fetch transactions: {error_msg}"})
                    return
            else:
                yield send_event("progress", {
                    "step": "fetched",
                    "message": "All transactions loaded from cache (no API call needed)",
                    "count": sum(len(t) for t in transactions_by_month.values())
                })

            # Ensure all months have an entry
            for ym in sorted_months:
                if ym not in transactions_by_month:
                    transactions_by_month[ym] = []

            await asyncio.sleep(0.1)

            # Step 2: Get parent folder and download all needed invoice folders
            parent_setting = db.query(AppSettings).filter(
                AppSettings.key == "invoice_parent_folder_id"
            ).first()

            invoices_by_month: dict[str, list] = {}
            file_id_maps: dict[str, dict] = {}

            if not _gdrive_service._credentials:
                yield send_event("error", {"message": "Not authenticated with Google Drive - please reconnect"})
                return

            if not parent_setting or not parent_setting.value:
                yield send_event("error", {"message": "Invoice parent folder not configured"})
                return

            if parent_setting and parent_setting.value:
                # Determine all folders we need (each month + previous month for first)
                folders_to_download = set()
                for ym in sorted_months:
                    folders_to_download.add(ym)
                # Add month before first for late payment matching
                first_y, first_m = map(int, first_month.split("-"))
                prev_date = datetime(first_y, first_m, 1) - __import__('datetime').timedelta(days=1)
                prev_month = f"{prev_date.year}-{prev_date.month:02d}"
                folders_to_download.add(prev_month)

                yield send_event("progress", {"step": "downloading", "message": f"Downloading invoices for {len(folders_to_download)} months..."})
                await asyncio.sleep(0.1)

                for ym in sorted(folders_to_download):
                    y, m = map(int, ym.split("-"))
                    subfolder_name = f"{y}{m:02d}"
                    subfolder = _gdrive_service.find_subfolder(parent_setting.value, subfolder_name)

                    if subfolder:
                        try:
                            invoice_dir, files, file_id_map = await asyncio.to_thread(
                                _gdrive_service.download_pdfs,
                                subfolder.id,
                                db,
                                True  # force_refresh for sync
                            )
                            file_id_maps[ym] = file_id_map

                            if invoice_dir:
                                invoices = await asyncio.to_thread(parse_invoices, invoice_dir)
                                for inv in invoices:
                                    inv.gdrive_file_id = file_id_map.get(inv.filename)
                                    inv.source_month = ym
                                invoices_by_month[ym] = invoices

                                yield send_event("progress", {
                                    "step": "downloaded_month",
                                    "message": f"Downloaded {len(invoices)} invoices for {ym}",
                                    "month": ym,
                                    "count": len(invoices)
                                })
                        except Exception as e:
                            yield send_event("progress", {
                                "step": "download_warning",
                                "message": f"Warning for {ym}: {sanitize_error(e)}"
                            })
                    else:
                        yield send_event("progress", {
                            "step": "folder_not_found",
                            "message": f"No folder found for {ym} ({subfolder_name})"
                        })

                await asyncio.sleep(0.1)

            # Step 3: Process each month
            known_service = KnownTransactionService(db)

            for ym in sorted_months:
                yield send_event("progress", {"step": "processing_month", "message": f"Processing {ym}...", "month": ym})
                await asyncio.sleep(0.1)

                y, m = map(int, ym.split("-"))
                prev_date = datetime(y, m, 1) - __import__('datetime').timedelta(days=1)
                prev_ym = f"{prev_date.year}-{prev_date.month:02d}"

                # Get or create month record
                month = db.query(MonthlyReconciliation).filter(
                    MonthlyReconciliation.year_month == ym
                ).first()

                # Get folder info
                subfolder_name = f"{y}{m:02d}"
                subfolder = None
                if parent_setting and parent_setting.value and _gdrive_service._credentials:
                    subfolder = _gdrive_service.find_subfolder(parent_setting.value, subfolder_name)

                if not month:
                    month = MonthlyReconciliation(
                        year_month=ym,
                        gdrive_folder_id=subfolder.id if subfolder else None,
                        gdrive_folder_name=subfolder.name if subfolder else None,
                        status="processing"
                    )
                    db.add(month)
                    db.commit()
                    db.refresh(month)
                else:
                    month.status = "processing"
                    if subfolder:
                        month.gdrive_folder_id = subfolder.id
                        month.gdrive_folder_name = subfolder.name
                    db.commit()

                # Get transactions for this month
                month_transactions = transactions_by_month.get(ym, [])

                # Combine invoices: current month + previous month
                month_invoices = list(invoices_by_month.get(ym, []))
                month_invoices.extend(invoices_by_month.get(prev_ym, []))

                # Separate fees, income, and check known transactions
                known_transactions = []
                unknown_transactions = []
                fee_transactions = []
                income_transactions = []

                for trans in month_transactions:
                    if trans.is_fee:
                        fee_transactions.append(trans)
                        continue
                    if trans.amount > 0:
                        income_transactions.append(trans)
                        continue
                    rule = known_service.match_transaction(trans)
                    if rule:
                        known_transactions.append((trans, rule))
                    else:
                        unknown_transactions.append(trans)

                # Separate invoices by type: cash (auto-paid), credit-notes, regular
                cash_invoices = [inv for inv in month_invoices if inv.is_cash]
                credit_note_invoices = [inv for inv in month_invoices if inv.is_credit_note and not inv.is_cash]
                regular_invoices = [inv for inv in month_invoices if not inv.is_credit_note and not inv.is_cash]

                # Match transactions with invoices
                matcher = Matcher()

                # Match regular invoices with expense transactions
                matched, unmatched_trans, unmatched_regular_inv = matcher.match_all(unknown_transactions, regular_invoices)

                # Match credit-note invoices with income transactions
                credit_matched, unmatched_income, unmatched_credit_inv = matcher.match_all(income_transactions, credit_note_invoices)

                # Combine results
                all_matched = matched + credit_matched
                all_unmatched_inv = unmatched_regular_inv + unmatched_credit_inv

                # Save results - include cash invoices as matched
                from decimal import Decimal
                matched_results = [
                    {
                        "transaction": serialize_transaction(m_result.transaction),
                        "invoice": serialize_invoice(m_result.invoice) if m_result.invoice else None,
                        "confidence": m_result.confidence,
                        "confidence_pct": m_result.confidence_pct,
                        "status": m_result.status,
                        "strategy_scores": m_result.strategy_scores,
                    }
                    for m_result in all_matched
                ]
                # Add cash invoices as matched (no transaction needed)
                for inv in cash_invoices:
                    if getattr(inv, 'source_month', ym) == ym:
                        matched_results.append({
                            "transaction": None,
                            "invoice": serialize_invoice(inv),
                            "confidence": 1.0,
                            "confidence_pct": 100,
                            "status": "OK",
                            "strategy_scores": {"CashPayment": 1.0},
                        })

                results = {
                    "matched": matched_results,
                    "unmatched": [serialize_transaction(t) for t in unmatched_trans],
                    "unmatched_invoices": [serialize_invoice(inv) for inv in all_unmatched_inv if getattr(inv, 'source_month', ym) == ym],
                    "known": [
                        {
                            **serialize_transaction(t),
                            "rule_reason": rule.reason,
                        }
                        for t, rule in known_transactions
                    ],
                    "fees": [serialize_transaction(t) for t in fee_transactions],
                    "income": [serialize_transaction(t) for t in unmatched_income],  # Only unmatched income
                }

                # Cache transactions for this month
                month.transactions_json = [
                    {
                        "id": t.id,
                        "date": str(t.date),
                        "amount": str(t.amount),
                        "currency": t.currency,
                        "counter_account": t.counter_account or "",
                        "counter_name": t.counter_name or "",
                        "vs": t.vs or "",
                        "note": t.note or "",
                        "transaction_type": t.transaction_type,
                        "raw_type": t.raw_type,
                    }
                    for t in month_transactions
                ]

                month.results_json = results
                # Count cash invoices from current month in matched count
                cash_from_month = len([inv for inv in cash_invoices if getattr(inv, 'source_month', ym) == ym])
                month.matched_count = len([m_result for m_result in all_matched if m_result.status == "OK"]) + cash_from_month
                month.review_count = len([m_result for m_result in all_matched if m_result.status == "REVIEW"])
                month.unmatched_count = len(unmatched_trans)
                month.known_count = len(known_transactions)
                month.fee_count = len(fee_transactions)
                month.income_count = len(unmatched_income)  # Only unmatched income
                month.status = "completed"
                month.last_synced_at = datetime.utcnow()
                month.error_message = None

                # Track invoice payments (includes credit notes)
                if subfolder:
                    db.query(InvoicePayment).filter(
                        InvoicePayment.invoice_month == ym
                    ).delete()

                for m_result in all_matched:
                    if m_result.invoice and m_result.invoice.gdrive_file_id:
                        source_month = getattr(m_result.invoice, 'source_month', ym)
                        if source_month == ym:
                            payment = InvoicePayment(
                                invoice_month=source_month,
                                gdrive_file_id=m_result.invoice.gdrive_file_id,
                                filename=m_result.invoice.filename,
                                receipt_index=m_result.invoice.receipt_index,
                                paid_month=ym,
                                transaction_id=m_result.transaction.id,
                                amount=Decimal(str(m_result.invoice.amount)) if m_result.invoice.amount else None,
                                vendor=m_result.invoice.vendor,
                            )
                            db.add(payment)
                        else:
                            existing = db.query(InvoicePayment).filter(
                                InvoicePayment.gdrive_file_id == m_result.invoice.gdrive_file_id,
                                InvoicePayment.receipt_index == m_result.invoice.receipt_index
                            ).first()
                            if existing:
                                existing.paid_month = ym
                                existing.transaction_id = m_result.transaction.id

                for inv in all_unmatched_inv:
                    if inv.gdrive_file_id and getattr(inv, 'source_month', ym) == ym:
                        payment = InvoicePayment(
                            invoice_month=ym,
                            gdrive_file_id=inv.gdrive_file_id,
                            filename=inv.filename,
                            receipt_index=inv.receipt_index,
                            paid_month=None,
                            transaction_id=None,
                            amount=Decimal(str(inv.amount)) if inv.amount else None,
                            vendor=inv.vendor,
                        )
                        db.add(payment)

                # Record cash invoices as paid
                for inv in cash_invoices:
                    if inv.gdrive_file_id and getattr(inv, 'source_month', ym) == ym:
                        payment = InvoicePayment(
                            invoice_month=ym,
                            gdrive_file_id=inv.gdrive_file_id,
                            filename=inv.filename,
                            receipt_index=inv.receipt_index,
                            paid_month=ym,  # Cash = paid immediately
                            transaction_id="CASH",
                            amount=Decimal(str(inv.amount)) if inv.amount else None,
                            vendor=inv.vendor,
                        )
                        db.add(payment)

                db.commit()

                yield send_event("month_complete", {
                    "month": ym,
                    "matched_count": month.matched_count,
                    "unmatched_count": month.unmatched_count,
                    "known_count": month.known_count
                })

            # Clean up downloaded files
            import shutil
            if parent_setting and parent_setting.value:
                for ym in invoices_by_month.keys():
                    y, m = map(int, ym.split("-"))
                    subfolder_name = f"{y}{m:02d}"
                    subfolder = _gdrive_service.find_subfolder(parent_setting.value, subfolder_name)
                    if subfolder:
                        download_dir = _gdrive_service._download_dir / subfolder.id
                        if download_dir.exists():
                            shutil.rmtree(download_dir, ignore_errors=True)

            yield send_event("complete", {
                "months": sorted_months,
                "total_months": len(sorted_months)
            })

        except Exception as e:
            # Reset any processing months to failed
            try:
                if 'sorted_months' in locals():
                    for ym in sorted_months:
                        m = db.query(MonthlyReconciliation).filter(
                            MonthlyReconciliation.year_month == ym,
                            MonthlyReconciliation.status == "processing"
                        ).first()
                        if m:
                            m.status = "failed"
                            m.error_message = sanitize_error(e)
                    db.commit()
            except Exception:
                pass
            yield send_event("error", {"message": sanitize_error(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
