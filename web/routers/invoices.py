"""Router for invoice endpoints."""

import hashlib
import re
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from web.auth import get_current_user
from web.database import get_db
from web.database.models import Invoice, Transaction, PDFCache, User, Vehicle
from web.routers.gdrive import get_gdrive_service_for_user
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
from web.services.vehicle_service import normalize_vehicle_registration
from web.routers.sse import send_progress, send_info, send_error, send_success
from parsers.pdf_parser import parse_uploaded_pdf

router = APIRouter(prefix="/api/invoices", tags=["invoices"])
VALID_DOCUMENT_TYPES = {"invoice", "receipt", "other"}


def _normalize_document_type(value: Optional[str]) -> str:
    """Normalize document type to a supported value."""
    if not value:
        return "invoice"

    normalized = value.strip().lower()
    if normalized in VALID_DOCUMENT_TYPES:
        return normalized
    return "invoice"


def _vehicle_registration_from_filename(filename: str) -> Optional[str]:
    """Extract an accountant-compatible registration from a filename."""
    match = re.search(r"(?<![A-Z0-9])([A-Z]{2}\d{3}[A-Z]{2})(?![A-Z0-9])", filename.upper())
    return match.group(1) if match else None


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
        document_type=_normalize_document_type(invoice.document_type),
        amount=invoice.amount,
        currency=invoice.currency or 'EUR',
        invoice_date=invoice.invoice_date,
        payment_type=invoice.payment_type,
        vs=invoice.vs,
        iban=invoice.iban,
        comment=invoice.comment,
        vehicle_id=invoice.vehicle_id,
        vehicle_registration=invoice.vehicle_registration,
        is_vehicle_expense=invoice.is_vehicle_expense,
        include_in_export=invoice.include_in_export,
        parent_invoice_id=invoice.parent_invoice_id,
        attachment_index=invoice.attachment_index,
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
    document_type: Optional[str] = Query(None, description="Filter by document type"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List invoices with optional filters."""
    query = db.query(Invoice).filter(Invoice.user_id == user.id)

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

    if document_type:
        query = query.filter(Invoice.document_type == _normalize_document_type(document_type))

    invoices = query.order_by(Invoice.invoice_date.desc()).all()

    # Attachments follow every matching primary document even when the active
    # status or document-type filter would normally hide reference rows.
    primary_ids = [invoice.id for invoice in invoices if invoice.parent_invoice_id is None]
    listed_ids = {invoice.id for invoice in invoices}
    if primary_ids:
        linked_attachments = db.query(Invoice).filter(
            Invoice.user_id == user.id,
            Invoice.parent_invoice_id.in_(primary_ids),
        ).order_by(Invoice.parent_invoice_id.asc(), Invoice.attachment_index.asc()).all()
        invoices.extend(
            attachment for attachment in linked_attachments if attachment.id not in listed_ids
        )

    unmatched = sum(1 for i in invoices if i.status == 'unmatched')
    matched = sum(1 for i in invoices if i.status == 'matched')
    attachment_count = sum(1 for i in invoices if i.parent_invoice_id is not None)

    return InvoiceListResponse(
        invoices=[_invoice_to_response(i) for i in invoices],
        total=len(invoices) - attachment_count,
        attachments=attachment_count,
        unmatched=unmatched,
        matched=matched,
    )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(
    invoice_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a single invoice by ID."""
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.user_id == user.id,
    ).first()
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
                "document_type": _normalize_document_type(parsed.get('document_type')),
                "amount": str(parsed['amount']) if parsed.get('amount') else None,
                "currency": parsed.get('currency', 'EUR'),
                "invoice_date": str(parsed['invoice_date']) if parsed.get('invoice_date') else None,
                "payment_type": parsed.get('payment_type'),
                "vs": parsed.get('vs'),
                "iban": parsed.get('iban'),
                "is_attachment": parsed.get('is_attachment', False),
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
    document_type: Optional[str] = Form(None),
    amount: Optional[str] = Form(None),
    currency: Optional[str] = Form(None),
    comment: Optional[str] = Form(None, max_length=2000),
    vehicle_id: Optional[int] = Form(None),
    vehicle_registration: Optional[str] = Form(None, max_length=16),
    is_vehicle_expense: bool = Form(False),
    include_in_export: bool = Form(True),
    parent_invoice_id: Optional[int] = Form(None),
    attachment_index: Optional[int] = Form(None),
    gdrive_folder_id: str = Form(...),  # Required - must specify GDrive folder
    skip_analyze: Optional[bool] = Form(False),  # Skip PDF analysis, use provided values
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload a PDF invoice to Google Drive and extract data.

    The file is always uploaded to Google Drive. GDrive authentication is required.
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    service = get_gdrive_service_for_user(db, user)

    # Save to temp file for parsing (use original filename for date extraction)
    content = await file.read()
    content_sha256 = hashlib.sha256(content).hexdigest()
    duplicate = db.query(Invoice).filter(
        Invoice.user_id == user.id,
        Invoice.content_sha256 == content_sha256,
    ).first()
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail=f"This PDF is already stored as {duplicate.filename}",
        )

    parent_invoice = None
    if parent_invoice_id is not None:
        parent_invoice = db.query(Invoice).filter(
            Invoice.id == parent_invoice_id,
            Invoice.user_id == user.id,
            Invoice.parent_invoice_id.is_(None),
        ).first()
        if not parent_invoice:
            raise HTTPException(status_code=400, detail="Select a valid primary document")
        if not attachment_index or attachment_index < 1:
            raise HTTPException(status_code=400, detail="Attachment index must be at least 1")
        if not parent_invoice.invoice_date:
            raise HTTPException(status_code=400, detail="Primary document has no invoice date")
        existing_attachment = db.query(Invoice).filter(
            Invoice.parent_invoice_id == parent_invoice.id,
            Invoice.attachment_index == attachment_index,
        ).first()
        if existing_attachment:
            raise HTTPException(
                status_code=409,
                detail=f"Attachment {attachment_index:02d} already exists",
            )

    selected_vehicle = None
    if parent_invoice is None and vehicle_id is not None:
        selected_vehicle = db.query(Vehicle).filter(
            Vehicle.id == vehicle_id,
            Vehicle.user_id == user.id,
            Vehicle.is_active.is_(True),
        ).first()
        if not selected_vehicle:
            raise HTTPException(status_code=400, detail="Select an active vehicle")

    if parent_invoice:
        final_vehicle_registration = None
    else:
        try:
            final_vehicle_registration = (
                selected_vehicle.registration
                if selected_vehicle
                else normalize_vehicle_registration(vehicle_registration)
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if parent_invoice is not None or not is_vehicle_expense:
        selected_vehicle = None
        final_vehicle_registration = None
        is_vehicle_expense = False
    if parent_invoice is None and is_vehicle_expense and not final_vehicle_registration:
        raise HTTPException(
            status_code=400,
            detail="Vehicle registration is required for a vehicle expense",
        )

    # Create temp file with original filename to enable filename-based date parsing
    import os
    temp_dir = tempfile.mkdtemp()
    tmp_path = Path(temp_dir) / file.filename
    tmp_path.write_bytes(content)

    try:
        # Parse the PDF (unless skip_analyze is set)
        parsed = {}
        if parent_invoice is None and not skip_analyze:
            try:
                parsed = parse_uploaded_pdf(tmp_path)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))

        # Use provided values or fall back to parsed
        final_vendor = parent_invoice.vendor if parent_invoice else vendor or parsed.get('vendor')
        final_date = None
        if parent_invoice:
            final_date = parent_invoice.invoice_date
        elif invoice_date:
            final_date = datetime.strptime(invoice_date, '%Y-%m-%d').date()
        elif parsed.get('invoice_date'):
            final_date = parsed['invoice_date']

        if final_date is None:
            raise HTTPException(status_code=400, detail="Could not determine invoice date")

        final_type = None if parent_invoice else payment_type or parsed.get('payment_type', 'card')
        final_document_type = 'other' if parent_invoice else _normalize_document_type(document_type or parsed.get('document_type'))
        final_currency = parent_invoice.currency if parent_invoice else currency or parsed.get('currency', 'EUR')
        # Use provided amount or fall back to parsed
        final_amount = None
        if parent_invoice:
            final_amount = None
        elif amount:
            final_amount = Decimal(amount)
        elif parsed.get('amount'):
            parsed_amount = parsed.get('amount')
            final_amount = Decimal(str(parsed_amount)) if not isinstance(parsed_amount, Decimal) else parsed_amount

        # Find or create month subfolder (YYYYMM format)
        month_folder_name = final_date.strftime('%Y%m')
        try:
            target_folder_id = service.find_or_create_subfolder(gdrive_folder_id, month_folder_name)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create month folder: {e}")

        # Generate proper filename: YYYY-MM-DD-NNN_type_vendor.pdf
        import re
        date_str = final_date.strftime('%Y-%m-%d')

        # Find next sequence number for this date
        existing_invoices = db.query(Invoice).filter(
            Invoice.invoice_date == final_date,
            Invoice.user_id == user.id,
            Invoice.parent_invoice_id.is_(None),
        ).all()
        next_seq = len(existing_invoices) + 1

        # Slugify vendor name
        vendor_slug = 'unknown'
        if final_vendor:
            vendor_slug = re.sub(r'[^\w\s-]', '', final_vendor.lower())
            vendor_slug = re.sub(r'[\s]+', '-', vendor_slug)[:30]

        if parent_invoice:
            parent_stem = Path(parent_invoice.filename).stem
            proper_filename = f"{parent_stem}_att_{attachment_index:02d}.pdf"
        else:
            plate_suffix = f"_{final_vehicle_registration}" if final_vehicle_registration else ""
            proper_filename = f"{date_str}-{next_seq:03d}_{final_type}_{vendor_slug}{plate_suffix}.pdf"

        # Upload to GDrive (to the month subfolder) with proper filename
        try:
            gdrive_file_id = service.upload_pdf(target_folder_id, proper_filename, content)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload to Google Drive: {e}")

        # Store PDF in cache so it's viewable
        cache_entry = PDFCache(
            user_id=user.id,
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
            user_id=user.id,
            gdrive_file_id=gdrive_file_id,
            receipt_index=0,
            filename=proper_filename,
            vendor=final_vendor,
            document_type=final_document_type,
            amount=final_amount,
            currency=final_currency,
            invoice_date=final_date,
            payment_type=final_type,
            vs=parsed.get('vs'),
            iban=parsed.get('iban'),
            comment=comment.strip() if comment and comment.strip() else None,
            vehicle_id=selected_vehicle.id if selected_vehicle else None,
            vehicle_registration=final_vehicle_registration,
            is_vehicle_expense=is_vehicle_expense,
            content_sha256=content_sha256,
            include_in_export=False if parent_invoice else include_in_export,
            parent_invoice_id=parent_invoice.id if parent_invoice else None,
            attachment_index=attachment_index if parent_invoice else None,
            is_credit_note=parsed.get('is_credit_note', False),
            status='unmatched' if include_in_export and not parent_invoice else 'reference',
            created_at=datetime.utcnow(),
        )

        db.add(invoice)
        db.commit()
        db.refresh(invoice)

        # Try auto-matching
        if not parent_invoice:
            matching = MatchingService(db, user.id)
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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List subfolders for import wizard."""
    service = get_gdrive_service_for_user(db, user)

    try:
        folders = service.list_folders(folder_id)
        return {
            "folders": [{"id": f.id, "name": f.name} for f in folders]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import-gdrive")
async def import_gdrive(
    request: ImportGDriveRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Import invoices from a GDrive folder (single folder, no recursion)."""
    service = get_gdrive_service_for_user(db, user)

    folder_id = request.folder_id
    send_info(user.id, "Listing files from Google Drive...", "import_gdrive")
    # Only import from the specified folder, not recursively
    files = service.list_pdfs(folder_id, recursive=False)

    total_files = len(files)
    send_info(user.id, f"Found {total_files} PDF files", "import_gdrive")

    imported = 0
    skipped = 0
    errors = 0

    for i, file_info in enumerate(files):
        send_progress(user.id, "import_gdrive", i + 1, total_files, f"Processing {file_info['name']}")
        gdrive_id = file_info['id']
        filename = file_info['name']

        # Check if already exists
        existing = db.query(Invoice).filter(
            Invoice.gdrive_file_id == gdrive_id,
            Invoice.receipt_index == 0,
            Invoice.user_id == user.id,
        ).first()

        if existing:
            skipped += 1
            continue

        # Download and parse
        try:
            content = service.download_file(gdrive_id)
            content_sha256 = hashlib.sha256(content).hexdigest()

            duplicate = db.query(Invoice).filter(
                Invoice.user_id == user.id,
                Invoice.content_sha256 == content_sha256,
            ).first()
            if duplicate:
                skipped += 1
                continue

            # Cache the PDF
            cache_entry = PDFCache(
                user_id=user.id,
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
                send_error(user.id, f"Error parsing {filename}: {e}", "import_gdrive")
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
            vehicle_registration = _vehicle_registration_from_filename(filename)
            vehicle = None
            if vehicle_registration:
                vehicle = db.query(Vehicle).filter(
                    Vehicle.user_id == user.id,
                    Vehicle.registration == vehicle_registration,
                ).first()
                if not vehicle:
                    vehicle = Vehicle(
                        user_id=user.id,
                        name=vehicle_registration,
                        registration=vehicle_registration,
                        is_active=True,
                    )
                    db.add(vehicle)
                    db.flush()
            invoice = Invoice(
                user_id=user.id,
                gdrive_file_id=gdrive_id,
                receipt_index=0,
                filename=filename,
                vendor=parsed.get('vendor'),
                document_type=_normalize_document_type(parsed.get('document_type')),
                amount=Decimal(str(parsed['amount'])) if parsed.get('amount') else None,
                currency=parsed.get('currency', 'EUR'),
                invoice_date=parsed.get('invoice_date'),
                payment_type=parsed.get('payment_type', 'card'),
                vs=parsed.get('vs'),
                iban=parsed.get('iban'),
                vehicle_id=vehicle.id if vehicle else None,
                vehicle_registration=vehicle_registration,
                is_vehicle_expense=bool(vehicle_registration),
                content_sha256=content_sha256,
                include_in_export=True,
                is_credit_note=parsed.get('is_credit_note', False),
                status='unmatched',
                created_at=datetime.utcnow(),
            )

            db.add(invoice)
            imported += 1

        except Exception as e:
            send_error(user.id, f"Error importing {filename}: {e}", "import_gdrive")
            errors += 1
            continue

    db.commit()

    # Run auto-matching on new invoices
    send_info(user.id, "Running auto-matching...", "import_gdrive")
    matching = MatchingService(db, user.id)
    match_results = matching.run_auto_matching()
    auto_matched = sum(match_results.values())

    send_success(user.id, f"Imported {imported} invoices, skipped {skipped}, {errors} errors, {auto_matched} auto-matched", "import_gdrive")

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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update invoice metadata."""
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.user_id == user.id,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    update_data = update.model_dump(exclude_unset=True)
    if "document_type" in update_data:
        update_data["document_type"] = _normalize_document_type(update_data["document_type"])
    if "vehicle_id" in update_data:
        next_vehicle_id = update_data.pop("vehicle_id")
        if next_vehicle_id is None:
            update_data["vehicle_id"] = None
            update_data["vehicle_registration"] = None
        else:
            selected_vehicle = db.query(Vehicle).filter(
                Vehicle.id == next_vehicle_id,
                Vehicle.user_id == user.id,
            ).first()
            if not selected_vehicle:
                raise HTTPException(status_code=400, detail="Select a valid vehicle")
            update_data["vehicle_id"] = selected_vehicle.id
            # The registration stored on an invoice is a historical snapshot.
            # Editing unrelated metadata must not rewrite old documents after a
            # vehicle registration is changed in Settings.
            update_data["vehicle_registration"] = (
                invoice.vehicle_registration
                if selected_vehicle.id == invoice.vehicle_id and invoice.vehicle_registration
                else selected_vehicle.registration
            )
    elif "vehicle_registration" in update_data:
        try:
            update_data["vehicle_registration"] = normalize_vehicle_registration(
                update_data["vehicle_registration"]
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    next_is_vehicle_expense = update_data.get(
        "is_vehicle_expense", invoice.is_vehicle_expense
    )
    next_vehicle_registration = update_data.get(
        "vehicle_registration", invoice.vehicle_registration
    )
    if next_is_vehicle_expense and not next_vehicle_registration:
        raise HTTPException(
            status_code=400,
            detail="Vehicle registration is required for a vehicle expense",
        )

    if update_data.get("include_in_export") is False and invoice.transaction_id:
        raise HTTPException(
            status_code=400,
            detail="Unmatch this document before excluding it from accountant export",
        )

    if update_data.get("is_vehicle_expense") is False:
        update_data["vehicle_id"] = None
        update_data["vehicle_registration"] = None

    if "include_in_export" in update_data:
        if update_data["include_in_export"] and not invoice.include_in_export:
            update_data["status"] = "unmatched"
        elif not update_data["include_in_export"]:
            update_data["status"] = "reference"
    for field, value in update_data.items():
        setattr(invoice, field, value)

    db.commit()
    db.refresh(invoice)
    return _invoice_to_response(invoice)


@router.delete("/{invoice_id}")
def delete_invoice(
    invoice_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete an invoice and its PDF from Google Drive."""
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.user_id == user.id,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    attachments = db.query(Invoice).filter(
        Invoice.parent_invoice_id == invoice.id,
        Invoice.user_id == user.id,
    ).order_by(Invoice.attachment_index.asc()).all()
    documents = [*attachments, invoice]

    # Delete the whole document group from GDrive first.
    gdrive_deleted = 0
    if any(document.gdrive_file_id for document in documents):
        service = get_gdrive_service_for_user(db, user)
        for document in documents:
            if not document.gdrive_file_id:
                continue
            try:
                service.delete_file(document.gdrive_file_id)
                gdrive_deleted += 1
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to delete from Google Drive: {e}")

    # Delete cached PDFs for the whole document group.
    for document in documents:
        if document.gdrive_file_id:
            cache = db.query(PDFCache).filter(
                PDFCache.gdrive_file_id == document.gdrive_file_id,
                PDFCache.user_id == user.id,
            ).first()
            if cache:
                db.delete(cache)

    # If matched, unmatch first
    if invoice.transaction_id:
        transaction = db.query(Transaction).filter(
            Transaction.id == invoice.transaction_id,
            Transaction.user_id == user.id,
        ).first()
        if transaction:
            transaction.status = 'unmatched'

    for attachment in attachments:
        db.delete(attachment)
    db.delete(invoice)
    db.commit()

    attachment_text = f" and {len(attachments)} attachments" if attachments else ""
    drive_text = " from GDrive" if gdrive_deleted else ""
    return {
        "success": True,
        "message": f"Invoice{attachment_text} deleted{drive_text}"
    }


@router.post("/{invoice_id}/match", response_model=InvoiceResponse)
def match_invoice(
    invoice_id: int,
    request: MatchRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Match an invoice to a transaction."""
    invoice_record = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.user_id == user.id,
    ).first()
    if not invoice_record:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if not invoice_record.include_in_export:
        raise HTTPException(
            status_code=400,
            detail="Internal reference files cannot be matched to bank transactions",
        )

    matching = MatchingService(db, user.id)

    try:
        invoice, _ = matching.match_invoice_to_transaction(
            invoice_id,
            request.transaction_id
        )
        return _invoice_to_response(invoice)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{invoice_id}/unmatch", response_model=InvoiceResponse)
def unmatch_invoice(
    invoice_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a match from an invoice."""
    matching = MatchingService(db, user.id)

    try:
        invoice = matching.unmatch_invoice(invoice_id)
        return _invoice_to_response(invoice)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{invoice_id}/reanalyze")
def reanalyze_invoice(
    invoice_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Re-parse the PDF and return extracted data (does not update the invoice)."""
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.user_id == user.id,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if not invoice.gdrive_file_id:
        raise HTTPException(status_code=400, detail="No PDF available for reanalysis")

    # Get PDF from cache
    cache = db.query(PDFCache).filter(
        PDFCache.gdrive_file_id == invoice.gdrive_file_id,
        PDFCache.user_id == user.id,
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
                "document_type": _normalize_document_type(parsed.get('document_type')),
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
def get_invoice_suggestions(
    invoice_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get match suggestions for an invoice."""
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.user_id == user.id,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    matching = MatchingService(db, user.id)
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
def get_invoice_pdf(
    invoice_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download the PDF for an invoice."""
    invoice = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.user_id == user.id,
    ).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if not invoice.gdrive_file_id:
        raise HTTPException(status_code=404, detail="No PDF available")

    # Check cache first (works for both local uploads and GDrive imports)
    cache = db.query(PDFCache).filter(
        PDFCache.gdrive_file_id == invoice.gdrive_file_id,
        PDFCache.user_id == user.id,
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
    service = get_gdrive_service_for_user(db, user)

    try:
        content = service.download_file(invoice.gdrive_file_id)

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
        db.commit()

        return Response(
            content=content,
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="{invoice.filename}"'}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to download PDF: {e}")
