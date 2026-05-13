"""Router for dashboard and export endpoints."""

import io
import zipfile
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from parsers.fio_api import fetch_monthly_statement_pdf
from web.auth import get_current_user
from web.database import get_db
from web.database.models import Invoice, Transaction, PDFCache, User
from web.routers.gdrive import get_gdrive_service_for_user

router = APIRouter(prefix="/api", tags=["dashboard"])
ACCOUNTANT_FOLDER_NAMES = {
    "receipt": "POKLADNICNE_DOKLADY",
    "invoice": "DOSLE_FAKTURY",
    "other": "OSTATNE",
}


class CopyToAccountantRequest(BaseModel):
    """Optional secrets required for accountant export."""

    fio_token: Optional[str] = None
    include_monthly_statement: bool = False


def _normalize_document_type(value: Optional[str]) -> str:
    """Normalize document type to a supported export bucket."""
    normalized = (value or "invoice").strip().lower()
    if normalized in ACCOUNTANT_FOLDER_NAMES:
        return normalized
    return "other"


def _get_or_create_accountant_subfolder(
    gdrive_service,
    root_folder_id: str,
    folder_name: str,
    target_folder_ids: dict[str, str],
    existing_files_by_folder: dict[str, set[str]],
) -> tuple[str, set[str]]:
    """Resolve an accountant subfolder and cache its existing filenames."""
    target_subfolder_id = target_folder_ids.get(folder_name)
    if target_subfolder_id is None:
        target_subfolder_id = gdrive_service.find_or_create_subfolder(root_folder_id, folder_name)
        target_folder_ids[folder_name] = target_subfolder_id
        try:
            existing_files_by_folder[folder_name] = set(
                gdrive_service.list_files_in_folder(target_subfolder_id)
            )
        except Exception:
            existing_files_by_folder[folder_name] = set()

    return target_subfolder_id, existing_files_by_folder[folder_name]


@router.get("/dashboard")
def get_dashboard(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get dashboard summary statistics."""
    # Unmatched transactions (expenses needing invoices)
    unmatched_transactions = db.query(Transaction).filter(
        Transaction.status == 'unmatched',
        Transaction.type == 'expense',
        Transaction.user_id == user.id,
    ).count()

    # Unmatched invoices (awaiting payment)
    unmatched_invoices = db.query(Invoice).filter(
        Invoice.status == 'unmatched',
        Invoice.user_id == user.id,
    ).count()

    # Get current month for "this month" stats
    today = datetime.utcnow().date()
    current_month_start = today.replace(day=1)

    # Matched this month
    matched_this_month = db.query(Invoice).filter(
        Invoice.status == 'matched',
        Invoice.invoice_date >= current_month_start,
        Invoice.user_id == user.id,
    ).count()

    # Ready to export (matched but not exported)
    ready_to_export = db.query(Invoice).filter(
        Invoice.status == 'matched',
        Invoice.user_id == user.id,
    ).count()

    # Known transactions
    known_transactions = db.query(Transaction).filter(
        Transaction.status == 'known',
        Transaction.user_id == user.id,
    ).count()

    # Skipped transactions
    skipped_transactions = db.query(Transaction).filter(
        Transaction.status == 'skipped',
        Transaction.user_id == user.id,
    ).count()

    # Get available months for filters
    invoice_months = db.query(
        func.strftime('%Y-%m', Invoice.invoice_date)
    ).filter(
        Invoice.invoice_date.isnot(None),
        Invoice.user_id == user.id,
    ).distinct().all()

    transaction_months = db.query(
        func.strftime('%Y-%m', Transaction.date)
    ).filter(
        Transaction.user_id == user.id,
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
    user: User = Depends(get_current_user),
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

    # Get matched/cash invoices for this month
    invoices = db.query(Invoice).filter(
        Invoice.status.in_(['matched', 'exported', 'cash']),
        Invoice.invoice_date >= start_date,
        Invoice.invoice_date <= end_date,
        Invoice.user_id == user.id,
    ).all()

    if not invoices:
        raise HTTPException(status_code=404, detail="No matched/cash invoices for this month")

    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    gdrive_service = None
    try:
        gdrive_service = get_gdrive_service_for_user(db, user)
    except HTTPException:
        gdrive_service = None

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for invoice in invoices:
            if not invoice.gdrive_file_id:
                continue

            # Get PDF from cache
            cache = db.query(PDFCache).filter(
                PDFCache.gdrive_file_id == invoice.gdrive_file_id,
                PDFCache.user_id == user.id,
            ).first()

            if cache:
                cache.last_accessed_at = datetime.utcnow()
                zf.writestr(invoice.filename, cache.content)
            else:
                # Try to download from GDrive
                try:
                    if gdrive_service:
                        content = gdrive_service.download_file(invoice.gdrive_file_id)
                        zf.writestr(invoice.filename, content)

                        # Cache it
                        cache_entry = PDFCache(
                            user_id=user.id,
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
def get_month_stats(
    year_month: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
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
        Invoice.invoice_date <= end_date,
        Invoice.user_id == user.id,
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
        Transaction.date <= end_date,
        Transaction.user_id == user.id,
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
def get_monthly_summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get income/expense summary for all months."""
    # Get all transactions grouped by month
    transactions = db.query(Transaction).filter(Transaction.user_id == user.id).all()

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
    cash_invoices = db.query(Invoice).filter(
        Invoice.status == 'cash',
        Invoice.user_id == user.id,
    ).all()
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
    payload: Optional[CopyToAccountantRequest] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Copy matched invoices to a shared GDrive folder (e.g., accountant folder)."""
    gdrive_service = get_gdrive_service_for_user(db, user)
    fio_token = (payload.fio_token or "").strip() if payload else ""
    include_monthly_statement = payload.include_monthly_statement if payload else False

    # Parse month
    try:
        year, mon = map(int, year_month.split('-'))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")

    from calendar import monthrange
    start_date = datetime(year, mon, 1).date()
    last_day = monthrange(year, mon)[1]
    end_date = datetime(year, mon, last_day).date()

    # Get matched/cash (non-exported) invoices for this month
    invoices = db.query(Invoice).filter(
        Invoice.status.in_(['matched', 'cash']),
        Invoice.invoice_date >= start_date,
        Invoice.invoice_date <= end_date,
        Invoice.gdrive_file_id.isnot(None),
        Invoice.user_id == user.id,
    ).all()

    if not invoices:
        raise HTTPException(status_code=404, detail="No matched/cash invoices to export for this month")

    copied = 0
    skipped = 0
    errors = []
    successful_exports = []
    target_folder_ids: dict[str, str] = {}
    existing_files_by_folder: dict[str, set[str]] = {}
    statement_status = "not_requested"
    statement_filename = f"fio_statement_{year}-{mon:02d}.pdf"

    for invoice in invoices:
        document_type = _normalize_document_type(invoice.document_type)
        target_folder_name = ACCOUNTANT_FOLDER_NAMES[document_type]

        try:
            target_subfolder_id, existing_files = _get_or_create_accountant_subfolder(
                gdrive_service,
                folder_id,
                target_folder_name,
                target_folder_ids,
                existing_files_by_folder,
            )
        except Exception as e:
            errors.append(f"{invoice.filename}: failed to resolve {target_folder_name} ({e})")
            continue

        if invoice.filename in existing_files:
            skipped += 1
            successful_exports.append(invoice)
            continue

        try:
            gdrive_service.copy_file(
                invoice.gdrive_file_id,
                target_subfolder_id,
                invoice.filename  # Keep same filename
            )
            copied += 1
            existing_files.add(invoice.filename)
            successful_exports.append(invoice)
        except Exception as e:
            errors.append(f"{invoice.filename}: {str(e)}")

    if include_monthly_statement:
        other_folder_name = ACCOUNTANT_FOLDER_NAMES["other"]
        try:
            if not fio_token:
                raise RuntimeError("Fio token is required to download the monthly statement")

            target_subfolder_id, existing_files = _get_or_create_accountant_subfolder(
                gdrive_service,
                folder_id,
                other_folder_name,
                target_folder_ids,
                existing_files_by_folder,
            )

            if statement_filename in existing_files:
                statement_status = "skipped"
            else:
                statement_content = fetch_monthly_statement_pdf(fio_token, year, mon)
                gdrive_service.upload_pdf(target_subfolder_id, statement_filename, statement_content)
                existing_files.add(statement_filename)
                statement_status = "uploaded"
        except Exception as e:
            statement_status = "failed"
            errors.append(f"{statement_filename}: {str(e)}")

    if mark_exported:
        for invoice in successful_exports:
            invoice.status = 'exported'
        db.commit()

    return {
        "success": True,
        "copied": copied,
        "skipped": skipped,
        "total": len(invoices),
        "errors": errors,
        "target_folders": sorted(target_folder_ids.keys()),
        "statement": {
            "filename": statement_filename,
            "status": statement_status,
        },
    }
