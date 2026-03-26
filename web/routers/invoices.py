"""Router for invoice endpoints."""

import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from web.database import get_db
from web.database.models import Invoice, Transaction, PDFCache
from web.schemas.invoices import (
    InvoiceResponse,
    InvoiceUpdate,
    InvoiceListResponse,
    InvoiceSuggestionsResponse,
    MatchSuggestion,
    MatchRequest,
    ImportGDriveRequest,
)
from web.services.matching_service import MatchingService
from web.routers.sse import send_progress, send_info, send_error, send_success
from parsers.pdf_parser import parse_uploaded_pdf

router = APIRouter(prefix="/api/invoices", tags=["invoices"])


def _invoice_to_response(invoice: Invoice) -> InvoiceResponse:
    """Convert Invoice model to response schema."""
    invoice_month = None
    if invoice.invoice_date:
        invoice_month = invoice.invoice_date.strftime('%Y-%m')

    return InvoiceResponse(
        id=invoice.id,
        gdrive_file_id=invoice.gdrive_file_id,
        receipt_index=invoice.receipt_index,
        filename=invoice.filename,
        vendor=invoice.vendor,
        amount=invoice.amount,
        currency=invoice.currency or 'EUR',
        invoice_date=invoice.invoice_date,
        payment_type=invoice.payment_type,
        vs=invoice.vs,
        iban=invoice.iban,
        is_credit_note=invoice.is_credit_note,
        status=invoice.status,
        transaction_id=invoice.transaction_id,
        created_at=invoice.created_at,
        invoice_month=invoice_month,
    )


@router.get("", response_model=InvoiceListResponse)
def list_invoices(
    month: Optional[str] = Query(None, description="Filter by month (YYYY-MM)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db)
):
    """List invoices with optional filters."""
    query = db.query(Invoice)

    if month:
        # Filter by invoice_date month
        year, mon = map(int, month.split('-'))
        from calendar import monthrange
        start_date = datetime(year, mon, 1).date()
        last_day = monthrange(year, mon)[1]
        end_date = datetime(year, mon, last_day).date()
        query = query.filter(
            Invoice.invoice_date >= start_date,
            Invoice.invoice_date <= end_date
        )

    if status:
        query = query.filter(Invoice.status == status)

    invoices = query.order_by(Invoice.invoice_date.desc()).all()

    unmatched = sum(1 for i in invoices if i.status == 'unmatched')
    matched = sum(1 for i in invoices if i.status == 'matched')

    return InvoiceListResponse(
        invoices=[_invoice_to_response(i) for i in invoices],
        total=len(invoices),
        unmatched=unmatched,
        matched=matched,
    )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    """Get a single invoice by ID."""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return _invoice_to_response(invoice)


@router.post("/analyze")
async def analyze_pdf(file: UploadFile = File(...)):
    """Analyze a PDF without saving - returns extracted data for preview."""
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    content = await file.read()

    import os
    temp_dir = tempfile.mkdtemp()
    tmp_path = Path(temp_dir) / file.filename
    tmp_path.write_bytes(content)

    try:
        parsed = parse_uploaded_pdf(tmp_path)
        return {
            "success": True,
            "extracted": {
                "vendor": parsed.get('vendor'),
                "amount": str(parsed['amount']) if parsed.get('amount') else None,
                "currency": parsed.get('currency', 'EUR'),
                "invoice_date": str(parsed['invoice_date']) if parsed.get('invoice_date') else None,
                "payment_type": parsed.get('payment_type'),
                "vs": parsed.get('vs'),
                "iban": parsed.get('iban'),
            }
        }
    except ValueError as e:
        # Return partial data even on error
        return {
            "success": False,
            "error": str(e),
            "extracted": {}
        }
    finally:
        tmp_path.unlink(missing_ok=True)
        os.rmdir(temp_dir)


@router.post("/upload", response_model=InvoiceResponse)
async def upload_invoice(
    file: UploadFile = File(...),
    vendor: Optional[str] = Form(None),
    invoice_date: Optional[str] = Form(None),
    payment_type: Optional[str] = Form(None),
    amount: Optional[str] = Form(None),
    currency: Optional[str] = Form(None),
    gdrive_folder_id: str = Form(...),  # Required - must specify GDrive folder
    skip_analyze: Optional[bool] = Form(False),  # Skip PDF analysis, use provided values
    db: Session = Depends(get_db)
):
    """Upload a PDF invoice to Google Drive and extract data.

    The file is always uploaded to Google Drive. GDrive authentication is required.
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    # Verify GDrive is authenticated
    from web.routers.gdrive import _gdrive_service
    if not _gdrive_service or not _gdrive_service._credentials:
        raise HTTPException(status_code=400, detail="Google Drive not connected. Please authenticate first.")

    # Save to temp file for parsing (use original filename for date extraction)
    content = await file.read()

    # Create temp file with original filename to enable filename-based date parsing
    import os
    temp_dir = tempfile.mkdtemp()
    tmp_path = Path(temp_dir) / file.filename
    tmp_path.write_bytes(content)

    try:
        # Parse the PDF (unless skip_analyze is set)
        parsed = {}
        if not skip_analyze:
            try:
                parsed = parse_uploaded_pdf(tmp_path)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

        # Use provided values or fall back to parsed
        final_vendor = vendor or parsed.get('vendor')
        final_date = None
        if invoice_date:
            final_date = datetime.strptime(invoice_date, '%Y-%m-%d').date()
        elif parsed.get('invoice_date'):
            final_date = parsed['invoice_date']

        if final_date is None:
            raise HTTPException(status_code=400, detail="Could not determine invoice date")

        final_type = payment_type or parsed.get('payment_type', 'card')
        final_currency = currency or parsed.get('currency', 'EUR')
        # Use provided amount or fall back to parsed
        final_amount = None
        if amount:
            final_amount = Decimal(amount)
        elif parsed.get('amount'):
            parsed_amount = parsed.get('amount')
            final_amount = Decimal(str(parsed_amount)) if not isinstance(parsed_amount, Decimal) else parsed_amount

        # Find or create month subfolder (YYYYMM format)
        month_folder_name = final_date.strftime('%Y%m')
        try:
            target_folder_id = _gdrive_service.find_or_create_subfolder(gdrive_folder_id, month_folder_name)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create month folder: {e}")

        # Generate proper filename: YYYY-MM-DD-NNN_type_vendor.pdf
        import re
        date_str = final_date.strftime('%Y-%m-%d')

        # Find next sequence number for this date
        existing_invoices = db.query(Invoice).filter(
            Invoice.invoice_date == final_date
        ).all()
        next_seq = len(existing_invoices) + 1

        # Slugify vendor name
        vendor_slug = 'unknown'
        if final_vendor:
            vendor_slug = re.sub(r'[^\w\s-]', '', final_vendor.lower())
            vendor_slug = re.sub(r'[\s]+', '-', vendor_slug)[:30]

        proper_filename = f"{date_str}-{next_seq:03d}_{final_type}_{vendor_slug}.pdf"

        # Upload to GDrive (to the month subfolder) with proper filename
        try:
            gdrive_file_id = _gdrive_service.upload_pdf(target_folder_id, proper_filename, content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload to Google Drive: {e}")

        # Store PDF in cache so it's viewable
        cache_entry = PDFCache(
            gdrive_file_id=gdrive_file_id,
            filename=proper_filename,
            content=content,
            file_size=len(content),
            cached_at=datetime.utcnow(),
            last_accessed_at=datetime.utcnow(),
        )
        db.add(cache_entry)

        # Create invoice record
        invoice = Invoice(
            gdrive_file_id=gdrive_file_id,
            receipt_index=0,
            filename=proper_filename,
            vendor=final_vendor,
            amount=final_amount,
            currency=final_currency,
            invoice_date=final_date,
            payment_type=final_type,
            vs=parsed.get('vs'),
            iban=parsed.get('iban'),
            is_credit_note=parsed.get('is_credit_note', False),
            status='unmatched',
            created_at=datetime.utcnow(),
        )

        db.add(invoice)
        db.commit()
        db.refresh(invoice)

        # Try auto-matching
        matching = MatchingService(db)
        matching.run_auto_matching()

        # Refresh to get updated status
        db.refresh(invoice)

        return _invoice_to_response(invoice)

    finally:
        tmp_path.unlink(missing_ok=True)
        os.rmdir(temp_dir)


@router.get("/import-gdrive/subfolders")
def list_import_subfolders(
    folder_id: str = Query(..., description="Parent folder ID"),
):
    """List subfolders for import wizard."""
    from web.routers.gdrive import _gdrive_service

    if not _gdrive_service or not _gdrive_service._credentials:
        raise HTTPException(status_code=503, detail="GDrive not connected")

    try:
        folders = _gdrive_service.list_folders(folder_id)
        return {
            "folders": [{"id": f.id, "name": f.name} for f in folders]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import-gdrive")
async def import_gdrive(
    request: ImportGDriveRequest,
    db: Session = Depends(get_db)
):
    """Import invoices from a GDrive folder (single folder, no recursion)."""
    from web.routers.gdrive import _gdrive_service

    if not _gdrive_service:
        send_error("GDrive service not available", "import_gdrive")
        raise HTTPException(status_code=503, detail="GDrive service not available")

    folder_id = request.folder_id
    send_info("Listing files from Google Drive...", "import_gdrive")
    # Only import from the specified folder, not recursively
    files = _gdrive_service.list_pdfs(folder_id, recursive=False)

    total_files = len(files)
    send_info(f"Found {total_files} PDF files", "import_gdrive")

    imported = 0
    skipped = 0
    errors = 0

    for i, file_info in enumerate(files):
        send_progress("import_gdrive", i + 1, total_files, f"Processing {file_info['name']}")
        gdrive_id = file_info['id']
        filename = file_info['name']

        # Check if already exists
        existing = db.query(Invoice).filter(
            Invoice.gdrive_file_id == gdrive_id,
            Invoice.receipt_index == 0
        ).first()

        if existing:
            skipped += 1
            continue

        # Download and parse
        try:
            content = _gdrive_service.download_file(gdrive_id)

            # Cache the PDF
            cache_entry = PDFCache(
                gdrive_file_id=gdrive_id,
                filename=filename,
                content=content,
                file_size=len(content),
                cached_at=datetime.utcnow(),
                last_accessed_at=datetime.utcnow(),
            )
            db.merge(cache_entry)

            # Parse - create temp file with original filename for date extraction
            import os
            temp_dir = tempfile.mkdtemp()
            tmp_path = Path(temp_dir) / filename
            tmp_path.write_bytes(content)

            try:
                parsed = parse_uploaded_pdf(tmp_path)
            except ValueError as e:
                send_error(f"Error parsing {filename}: {e}", "import_gdrive")
                errors += 1
                tmp_path.unlink(missing_ok=True)
                os.rmdir(temp_dir)
                continue
            finally:
                if tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
                if Path(temp_dir).exists():
                    os.rmdir(temp_dir)

            # Create invoice
            invoice = Invoice(
                gdrive_file_id=gdrive_id,
                receipt_index=0,
                filename=filename,
                vendor=parsed.get('vendor'),
                amount=Decimal(str(parsed['amount'])) if parsed.get('amount') else None,
                currency=parsed.get('currency', 'EUR'),
                invoice_date=parsed.get('invoice_date'),
                payment_type=parsed.get('payment_type', 'card'),
                vs=parsed.get('vs'),
                iban=parsed.get('iban'),
                is_credit_note=parsed.get('is_credit_note', False),
                status='unmatched',
                created_at=datetime.utcnow(),
            )

            db.add(invoice)
            imported += 1

        except Exception as e:
            send_error(f"Error importing {filename}: {e}", "import_gdrive")
            errors += 1
            continue

    db.commit()

    # Run auto-matching on new invoices
    send_info("Running auto-matching...", "import_gdrive")
    matching = MatchingService(db)
    match_results = matching.run_auto_matching()
    auto_matched = sum(match_results.values())

    send_success(f"Imported {imported} invoices, skipped {skipped}, {errors} errors, {auto_matched} auto-matched", "import_gdrive")

    return {
        "success": True,
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "auto_matched": auto_matched,
    }


@router.patch("/{invoice_id}", response_model=InvoiceResponse)
def update_invoice(
    invoice_id: int,
    update: InvoiceUpdate,
    db: Session = Depends(get_db)
):
    """Update invoice metadata."""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    update_data = update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(invoice, field, value)

    db.commit()
    db.refresh(invoice)
    return _invoice_to_response(invoice)


@router.delete("/{invoice_id}")
def delete_invoice(invoice_id: int, db: Session = Depends(get_db)):
    """Delete an invoice and its PDF from Google Drive."""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Delete from GDrive first
    gdrive_deleted = False
    if invoice.gdrive_file_id:
        from web.routers.gdrive import _gdrive_service
        if not _gdrive_service or not _gdrive_service._credentials:
            raise HTTPException(
                status_code=400,
                detail="Google Drive not connected. Cannot delete invoice without deleting the PDF from GDrive."
            )

        try:
            _gdrive_service.delete_file(invoice.gdrive_file_id)
            gdrive_deleted = True
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete from Google Drive: {e}")

    # Delete from PDF cache
    if invoice.gdrive_file_id:
        cache = db.query(PDFCache).filter(
            PDFCache.gdrive_file_id == invoice.gdrive_file_id
        ).first()
        if cache:
            db.delete(cache)

    # If matched, unmatch first
    if invoice.transaction_id:
        transaction = db.query(Transaction).filter(
            Transaction.id == invoice.transaction_id
        ).first()
        if transaction:
            transaction.status = 'unmatched'

    db.delete(invoice)
    db.commit()

    return {
        "success": True,
        "message": "Invoice deleted" + (" from GDrive" if gdrive_deleted else "")
    }


@router.post("/{invoice_id}/match", response_model=InvoiceResponse)
def match_invoice(
    invoice_id: int,
    request: MatchRequest,
    db: Session = Depends(get_db)
):
    """Match an invoice to a transaction."""
    matching = MatchingService(db)

    try:
        invoice, _ = matching.match_invoice_to_transaction(
            invoice_id,
            request.transaction_id
        )
        return _invoice_to_response(invoice)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{invoice_id}/unmatch", response_model=InvoiceResponse)
def unmatch_invoice(invoice_id: int, db: Session = Depends(get_db)):
    """Remove a match from an invoice."""
    matching = MatchingService(db)

    try:
        invoice = matching.unmatch_invoice(invoice_id)
        return _invoice_to_response(invoice)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{invoice_id}/reanalyze")
def reanalyze_invoice(invoice_id: int, db: Session = Depends(get_db)):
    """Re-parse the PDF and return extracted data (does not update the invoice)."""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if not invoice.gdrive_file_id:
        raise HTTPException(status_code=400, detail="No PDF available for reanalysis")

    # Get PDF from cache
    cache = db.query(PDFCache).filter(
        PDFCache.gdrive_file_id == invoice.gdrive_file_id
    ).first()

    if not cache:
        raise HTTPException(status_code=404, detail="PDF not in cache - import from GDrive first")

    # Parse the PDF with original filename for date extraction
    import os
    temp_dir = tempfile.mkdtemp()
    tmp_path = Path(temp_dir) / invoice.filename
    tmp_path.write_bytes(cache.content)

    try:
        parsed = parse_uploaded_pdf(tmp_path)
        return {
            "success": True,
            "extracted": {
                "vendor": parsed.get('vendor'),
                "amount": str(parsed['amount']) if parsed.get('amount') else None,
                "currency": parsed.get('currency', 'EUR'),
                "invoice_date": str(parsed['invoice_date']) if parsed.get('invoice_date') else None,
                "payment_type": parsed.get('payment_type'),
                "vs": parsed.get('vs'),
                "iban": parsed.get('iban'),
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        tmp_path.unlink(missing_ok=True)
        os.rmdir(temp_dir)


@router.get("/{invoice_id}/suggestions", response_model=InvoiceSuggestionsResponse)
def get_invoice_suggestions(invoice_id: int, db: Session = Depends(get_db)):
    """Get match suggestions for an invoice."""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    matching = MatchingService(db)
    suggestions = matching.suggest_matches_for_invoice(invoice)

    return InvoiceSuggestionsResponse(
        invoice_id=invoice_id,
        suggestions=[
            MatchSuggestion(
                transaction_id=t.id,
                date=t.date,
                amount=t.amount,
                counter_name=t.counter_name,
                vs=t.vs,
                note=t.note,
                extracted_vendor=t.extracted_vendor,
                score=breakdown['score'],
                amount_score=breakdown['amount_score'],
                date_score=breakdown['date_score'],
                vendor_score=breakdown['vendor_score'],
                date_diff_days=breakdown['date_diff_days'],
            )
            for t, breakdown in suggestions
        ]
    )


@router.get("/{invoice_id}/pdf")
def get_invoice_pdf(invoice_id: int, db: Session = Depends(get_db)):
    """Download the PDF for an invoice."""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if not invoice.gdrive_file_id:
        raise HTTPException(status_code=404, detail="No PDF available")

    # Check cache first (works for both local uploads and GDrive imports)
    cache = db.query(PDFCache).filter(
        PDFCache.gdrive_file_id == invoice.gdrive_file_id
    ).first()

    if cache:
        cache.last_accessed_at = datetime.utcnow()
        db.commit()
        return Response(
            content=cache.content,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{invoice.filename}"'}
        )

    # Download from GDrive if not in cache
    from web.routers.gdrive import _gdrive_service
    if not _gdrive_service:
        raise HTTPException(status_code=503, detail="GDrive service not available")

    try:
        content = _gdrive_service.download_file(invoice.gdrive_file_id)

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
        db.commit()

        return Response(
            content=content,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{invoice.filename}"'}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download PDF: {e}")
