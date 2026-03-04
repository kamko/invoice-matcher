"""SSE-based reconciliation for real-time progress updates."""

import asyncio
import json
from pathlib import Path
from typing import AsyncGenerator
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from web.database import get_db
from web.database.models import ReconciliationSession
from web.services.known_trans_service import KnownTransactionService
from web.routers.gdrive import _gdrive_service
from web.config import DATA_DIR

from models.transaction import Transaction
from parsers.fio_api import fetch_transactions_from_api
from parsers.pdf_parser import parse_invoices
from matching.matcher import Matcher

router = APIRouter(prefix="/api", tags=["reconciliation-sse"])


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
                yield send_event("error", {"message": f"Failed to fetch transactions: {e}"})
                session.status = "failed"
                session.error_message = str(e)
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
                        invoice_dir, files = await asyncio.to_thread(
                            _gdrive_service.download_pdfs,
                            request.gdrive_folder_id
                        )
                        yield send_event("progress", {
                            "step": "downloaded",
                            "message": f"Downloaded {len(files)} PDF files",
                            "count": len(files)
                        })
                    except Exception as e:
                        yield send_event("error", {"message": f"Failed to download: {e}"})
                        session.status = "failed"
                        session.error_message = str(e)
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
                        "rule_category": rule.category,
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
            yield send_event("error", {"message": str(e)})

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
    }
