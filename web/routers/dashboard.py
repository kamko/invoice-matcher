"""Router for dashboard and export endpoints."""

import io
import zipfile
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from web.database import get_db
from web.database.models import Invoice, Transaction, PDFCache

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def get_dashboard(db: Session = Depends(get_db)):
    """Get dashboard summary statistics."""
    # Unmatched transactions (expenses needing invoices)
    unmatched_transactions = db.query(Transaction).filter(
        Transaction.status == 'unmatched',
        Transaction.type == 'expense'
    ).count()

    # Unmatched invoices (awaiting payment)
    unmatched_invoices = db.query(Invoice).filter(
        Invoice.status == 'unmatched'
    ).count()

    # Get current month for "this month" stats
    today = datetime.utcnow().date()
    current_month_start = today.replace(day=1)

    # Matched this month
    matched_this_month = db.query(Invoice).filter(
        Invoice.status == 'matched',
        Invoice.invoice_date >= current_month_start
    ).count()

    # Ready to export (matched but not exported)
    ready_to_export = db.query(Invoice).filter(
        Invoice.status == 'matched'
    ).count()

    # Known transactions
    known_transactions = db.query(Transaction).filter(
        Transaction.status == 'known'
    ).count()

    # Skipped transactions
    skipped_transactions = db.query(Transaction).filter(
        Transaction.status == 'skipped'
    ).count()

    # Get available months for filters
    invoice_months = db.query(
        func.strftime('%Y-%m', Invoice.invoice_date)
    ).filter(
        Invoice.invoice_date.isnot(None)
    ).distinct().all()

    transaction_months = db.query(
        func.strftime('%Y-%m', Transaction.date)
    ).distinct().all()

    all_months = sorted(set(
        [m[0] for m in invoice_months if m[0]] +
        [m[0] for m in transaction_months if m[0]]
    ), reverse=True)

    return {
        "unmatched_transactions": unmatched_transactions,
        "unmatched_invoices": unmatched_invoices,
        "matched_this_month": matched_this_month,
        "ready_to_export": ready_to_export,
        "known_transactions": known_transactions,
        "skipped_transactions": skipped_transactions,
        "available_months": all_months,
    }


@router.get("/export/{year_month}")
def export_month(
    year_month: str,
    mark_exported: bool = Query(False, description="Mark invoices as exported"),
    db: Session = Depends(get_db)
):
    """Download a ZIP of matched invoices for a month."""
    # Parse month
    try:
        year, mon = map(int, year_month.split('-'))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")

    from calendar import monthrange
    start_date = datetime(year, mon, 1).date()
    last_day = monthrange(year, mon)[1]
    end_date = datetime(year, mon, last_day).date()

    # Get matched invoices for this month
    invoices = db.query(Invoice).filter(
        Invoice.status.in_(['matched', 'exported']),
        Invoice.invoice_date >= start_date,
        Invoice.invoice_date <= end_date
    ).all()

    if not invoices:
        raise HTTPException(status_code=404, detail="No matched invoices for this month")

    # Create ZIP in memory
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for invoice in invoices:
            if not invoice.gdrive_file_id:
                continue

            # Get PDF from cache
            cache = db.query(PDFCache).filter(
                PDFCache.gdrive_file_id == invoice.gdrive_file_id
            ).first()

            if cache:
                cache.last_accessed_at = datetime.utcnow()
                zf.writestr(invoice.filename, cache.content)
            else:
                # Try to download from GDrive
                try:
                    from web.routers.gdrive import _gdrive_service
                    if _gdrive_service:
                        content = _gdrive_service.download_file(invoice.gdrive_file_id)
                        zf.writestr(invoice.filename, content)

                        # Cache it
                        cache_entry = PDFCache(
                            gdrive_file_id=invoice.gdrive_file_id,
                            filename=invoice.filename,
                            content=content,
                            file_size=len(content),
                            cached_at=datetime.utcnow(),
                            last_accessed_at=datetime.utcnow(),
                        )
                        db.merge(cache_entry)
                except Exception as e:
                    print(f"Error downloading {invoice.filename}: {e}")
                    continue

    if mark_exported:
        for invoice in invoices:
            invoice.status = 'exported'
        db.commit()
    else:
        db.commit()  # For cache updates

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="invoices_{year_month}.zip"'
        }
    )


@router.get("/stats/{year_month}")
def get_month_stats(year_month: str, db: Session = Depends(get_db)):
    """Get statistics for a specific month."""
    try:
        year, mon = map(int, year_month.split('-'))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")

    from calendar import monthrange
    start_date = datetime(year, mon, 1).date()
    last_day = monthrange(year, mon)[1]
    end_date = datetime(year, mon, last_day).date()

    # Invoice stats for this month (by invoice_date)
    invoices = db.query(Invoice).filter(
        Invoice.invoice_date >= start_date,
        Invoice.invoice_date <= end_date
    ).all()

    invoice_stats = {
        "total": len(invoices),
        "unmatched": sum(1 for i in invoices if i.status == 'unmatched'),
        "matched": sum(1 for i in invoices if i.status == 'matched'),
        "exported": sum(1 for i in invoices if i.status == 'exported'),
        "cash": sum(1 for i in invoices if i.status == 'cash'),
    }

    # Transaction stats for this month (by transaction date)
    transactions = db.query(Transaction).filter(
        Transaction.date >= start_date,
        Transaction.date <= end_date
    ).all()

    transaction_stats = {
        "total": len(transactions),
        "unmatched": sum(1 for t in transactions if t.status == 'unmatched'),
        "matched": sum(1 for t in transactions if t.status == 'matched'),
        "known": sum(1 for t in transactions if t.status == 'known'),
        "skipped": sum(1 for t in transactions if t.status == 'skipped'),
        "expenses": sum(1 for t in transactions if t.type == 'expense'),
        "income": sum(1 for t in transactions if t.type == 'income'),
        "fees": sum(1 for t in transactions if t.type == 'fee'),
    }

    return {
        "year_month": year_month,
        "invoices": invoice_stats,
        "transactions": transaction_stats,
    }
