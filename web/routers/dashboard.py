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

    # Calculate amounts
    income_total = sum(float(t.amount) for t in transactions if t.type == 'income')
    expense_total = sum(float(t.amount) for t in transactions if t.type == 'expense')
    fee_total = sum(float(t.amount) for t in transactions if t.type == 'fee')

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

    # Amount summary
    amounts = {
        "income": round(income_total, 2),
        "expenses": round(expense_total, 2),
        "fees": round(fee_total, 2),
        "net": round(income_total + expense_total + fee_total, 2),  # expenses and fees are negative
    }

    return {
        "year_month": year_month,
        "invoices": invoice_stats,
        "transactions": transaction_stats,
        "amounts": amounts,
    }


@router.get("/monthly-summary")
def get_monthly_summary(db: Session = Depends(get_db)):
    """Get income/expense summary for all months."""
    # Get all transactions grouped by month
    transactions = db.query(Transaction).all()

    # Group by month
    monthly_data = {}
    for t in transactions:
        month_key = t.date.strftime('%Y-%m')
        if month_key not in monthly_data:
            monthly_data[month_key] = {"income": 0, "expenses": 0, "fees": 0, "cash": 0}

        amount = float(t.amount)
        if t.type == 'income':
            monthly_data[month_key]["income"] += amount
        elif t.type == 'expense':
            monthly_data[month_key]["expenses"] += amount
        elif t.type == 'fee':
            monthly_data[month_key]["fees"] += amount

    # Add cash invoices (no bank transaction)
    cash_invoices = db.query(Invoice).filter(Invoice.status == 'cash').all()
    for inv in cash_invoices:
        if inv.invoice_date and inv.amount:
            month_key = inv.invoice_date.strftime('%Y-%m')
            if month_key not in monthly_data:
                monthly_data[month_key] = {"income": 0, "expenses": 0, "fees": 0, "cash": 0}
            # Cash invoices are expenses (negative)
            monthly_data[month_key]["cash"] -= float(inv.amount)

    # Convert to list and calculate net
    result = []
    for month, data in sorted(monthly_data.items(), reverse=True):
        result.append({
            "month": month,
            "income": round(data["income"], 2),
            "expenses": round(data["expenses"], 2),
            "fees": round(data["fees"], 2),
            "cash": round(data["cash"], 2),
            "net": round(data["income"] + data["expenses"] + data["fees"] + data["cash"], 2),
        })

    return {"months": result}


@router.post("/export/{year_month}/copy-to-gdrive")
def copy_to_accountant_folder(
    year_month: str,
    folder_id: str = Query(..., description="Target GDrive folder ID"),
    mark_exported: bool = Query(False, description="Mark invoices as exported"),
    db: Session = Depends(get_db)
):
    """Copy matched invoices to a shared GDrive folder (e.g., accountant folder)."""
    from web.routers.gdrive import _gdrive_service

    if not _gdrive_service or not _gdrive_service._credentials:
        raise HTTPException(status_code=400, detail="Google Drive not connected")

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
        Invoice.invoice_date <= end_date,
        Invoice.gdrive_file_id.isnot(None)
    ).all()

    if not invoices:
        raise HTTPException(status_code=404, detail="No matched invoices for this month")

    # Find or create month subfolder in target folder (YYYYMM format)
    month_folder_name = f"{year}{mon:02d}"
    try:
        target_subfolder_id = _gdrive_service.find_or_create_subfolder(folder_id, month_folder_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create month folder: {e}")

    copied = 0
    errors = []

    for invoice in invoices:
        try:
            _gdrive_service.copy_file(
                invoice.gdrive_file_id,
                target_subfolder_id,
                invoice.filename  # Keep same filename
            )
            copied += 1
        except Exception as e:
            errors.append(f"{invoice.filename}: {str(e)}")

    if mark_exported:
        for invoice in invoices:
            invoice.status = 'exported'
        db.commit()

    return {
        "success": True,
        "copied": copied,
        "total": len(invoices),
        "errors": errors,
        "target_folder": month_folder_name,
    }
