"""Router for reconciliation endpoints."""

import tempfile
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from web.database import get_db
from web.schemas.reconciliation import (
    ReconcileRequest,
    ReconcileResponse,
    SessionResponse,
    MarkKnownRequest,
    MatchWithPdfResponse,
    MonthlyReconcileRequest,
    MonthResponse,
    MonthListItem,
    SetFolderRequest,
)
from parsers.pdf_parser import parse_uploaded_pdf
from web.database.models import MonthlyReconciliation, InvoicePayment, AppSettings
from web.schemas.known_transaction import KnownTransactionCreate
from web.services.reconcile_service import ReconcileService
from web.services.known_trans_service import KnownTransactionService
from web.routers.gdrive import _gdrive_service  # Use the authenticated instance
from web.config import DATA_DIR

router = APIRouter(prefix="/api", tags=["reconciliation"])


def run_reconciliation_task(
    session_id: int,
    fio_token: str,
    invoice_dir: Path | None,
    db_url: str
):
    """Background task to run reconciliation."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        service = ReconcileService(db)
        session = service.get_session(session_id)
        if session:
            service.run_reconciliation(session, fio_token, invoice_dir)
    finally:
        db.close()


@router.post("/reconcile", response_model=ReconcileResponse)
def start_reconciliation(
    request: ReconcileRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Start a new reconciliation process."""
    service = ReconcileService(db)

    # Create session
    session = service.create_session(request)

    # Determine invoice directory
    invoice_dir = None
    if request.invoice_dir:
        invoice_dir = Path(request.invoice_dir)
        if not invoice_dir.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Invoice directory not found: {request.invoice_dir}"
            )
    elif request.gdrive_folder_id:
        # GDrive folder - download using the authenticated service
        if _gdrive_service.is_available:
            if not _gdrive_service._credentials:
                raise HTTPException(
                    status_code=401,
                    detail="Not authenticated with Google Drive. Please connect first."
                )
            try:
                invoice_dir, downloaded_files, _ = _gdrive_service.download_pdfs(request.gdrive_folder_id, db, force_refresh=True)
                if not downloaded_files:
                    raise HTTPException(
                        status_code=400,
                        detail="No PDF files found in the selected folder"
                    )
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to download from Google Drive: {e}"
                )

    # Run reconciliation in background
    from web.database.connection import DATABASE_URL
    background_tasks.add_task(
        run_reconciliation_task,
        session.id,
        request.fio_token,
        invoice_dir,
        DATABASE_URL
    )

    return ReconcileResponse(
        session_id=session.id,
        status="processing",
        message="Reconciliation started"
    )


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: int, db: Session = Depends(get_db)):
    """Get reconciliation session with results."""
    service = ReconcileService(db)
    session = service.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    results = service.get_session_results(session)

    fees = results.get("fees", [])
    income = results.get("income", [])
    return SessionResponse(
        id=session.id,
        from_date=session.from_date,
        to_date=session.to_date,
        status=session.status,
        created_at=session.created_at,
        completed_at=session.completed_at,
        matched_count=session.matched_count,
        unmatched_count=session.unmatched_count,
        review_count=session.review_count,
        known_count=session.known_count,
        fee_count=len(fees),
        income_count=len(income),
        matched=results.get("matched", []),
        unmatched=results.get("unmatched", []),
        known=results.get("known", []),
        fees=fees,
        income=income,
        unmatched_invoices=results.get("unmatched_invoices", []),
        error_message=session.error_message,
    )


@router.post("/sessions/{session_id}/mark-known")
def mark_as_known(
    session_id: int,
    request: MarkKnownRequest,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Mark a transaction as known by creating a rule."""
    reconcile_service = ReconcileService(db)
    known_service = KnownTransactionService(db)

    session = reconcile_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Create the known transaction rule
    rule_data = KnownTransactionCreate(
        rule_type=request.rule_type,
        reason=request.reason,
        vendor_pattern=request.vendor_pattern,
        note_pattern=request.note_pattern,
        amount=request.amount,
        amount_min=request.amount_min,
        amount_max=request.amount_max,
        counter_account=request.counter_account,
    )

    rule = known_service.create(rule_data)

    # Update session results to move ALL matching transactions to known
    if session.results_json:
        results = session.results_json.copy()

        unmatched = results.get("unmatched", [])
        known = results.get("known", [])

        # Find all transactions that match the new rule
        new_unmatched = []
        matched_count = 0

        for trans in unmatched:
            # Check if this transaction matches the rule
            matches = False

            if request.rule_type == "note" and request.note_pattern:
                import re
                try:
                    pattern = re.compile(request.note_pattern, re.IGNORECASE)
                    note = trans.get("note") or ""
                    matches = bool(pattern.search(note))
                except re.error:
                    pass
            elif request.rule_type == "vendor" and request.vendor_pattern:
                import re
                try:
                    pattern = re.compile(request.vendor_pattern, re.IGNORECASE)
                    text = f"{trans.get('counter_name', '')} {trans.get('note', '')}"
                    matches = bool(pattern.search(text))
                except re.error:
                    pass
            elif request.rule_type == "exact":
                # Exact match - only the clicked transaction
                matches = trans.get("id") == request.transaction_id

            if matches:
                trans["rule_reason"] = request.reason
                known.append(trans)
                matched_count += 1
            else:
                new_unmatched.append(trans)

        results["unmatched"] = new_unmatched
        results["known"] = known

        session.results_json = results
        session.unmatched_count = len(new_unmatched)
        session.known_count = len(known)
        flag_modified(session, "results_json")
        db.commit()

    return {
        "success": True,
        "rule_id": rule.id,
        "message": "Transaction marked as known"
    }


@router.post("/sessions/{session_id}/match-with-pdf", response_model=MatchWithPdfResponse)
async def match_with_pdf(
    session_id: int,
    transaction_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Match an unmatched transaction with an uploaded PDF invoice.

    Uploads the PDF to Google Drive (if gdrive_folder_id is set) and creates a match.
    """
    reconcile_service = ReconcileService(db)
    session = reconcile_service.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    # Read file content
    content = await file.read()

    # Save to temp file for parsing
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        # First, find the transaction to get its payment type
        transaction_data = None
        if session.results_json:
            unmatched = session.results_json.get("unmatched", [])
            for trans in unmatched:
                if trans.get("id") == transaction_id:
                    transaction_data = trans
                    break

        if not transaction_data:
            raise HTTPException(status_code=404, detail="Transaction not found in unmatched list")

        # Get payment type from transaction (card or wire)
        payment_type = transaction_data.get("transaction_type", "unknown")

        # Parse the PDF (use uploaded parser that extracts from content)
        invoice = parse_uploaded_pdf(tmp_path)
        if not invoice:
            raise HTTPException(status_code=400, detail="Could not extract data from PDF. Make sure it contains text (not scanned image).")

        # Generate proper filename based on invoice + transaction data
        # Format: YYYY-MM-DD-NNN_type_vendor.pdf
        invoice_date_str = str(invoice.invoice_date) if invoice.invoice_date else "unknown"
        vendor_slug = (invoice.vendor or "unknown").lower().replace(" ", "-")[:20]

        # Find next sequence number
        sequence_num = 1
        gdrive_file_id = None

        if session.gdrive_folder_id and _gdrive_service._credentials:
            try:
                # List existing files to find next sequence number for this date
                existing_files = _gdrive_service.list_files_in_folder(session.gdrive_folder_id)
                date_prefix = f"{invoice_date_str}-"

                # Find max sequence for this date
                for fname in existing_files:
                    if fname.startswith(date_prefix):
                        # Extract sequence: YYYY-MM-DD-NNN_...
                        parts = fname.split("_")
                        if parts:
                            try:
                                seq = int(parts[0].split("-")[-1])
                                if seq >= sequence_num:
                                    sequence_num = seq + 1
                            except (ValueError, IndexError):
                                pass

                # Generate filename with correct sequence
                gdrive_filename = f"{invoice_date_str}-{sequence_num:03d}_{payment_type}_{vendor_slug}.pdf"

                # Upload
                gdrive_file_id = _gdrive_service.upload_pdf(
                    session.gdrive_folder_id,
                    gdrive_filename,
                    content
                )
            except Exception as e:
                # Continue even if upload fails, use default sequence
                gdrive_filename = f"{invoice_date_str}-{sequence_num:03d}_{payment_type}_{vendor_slug}.pdf"
        else:
            gdrive_filename = f"{invoice_date_str}-{sequence_num:03d}_{payment_type}_{vendor_slug}.pdf"

        # Serialize invoice data (merge with transaction payment type)
        invoice_data = {
            "file_path": gdrive_filename if gdrive_file_id else str(invoice.file_path),
            "filename": gdrive_filename,
            "invoice_date": str(invoice.invoice_date) if invoice.invoice_date else None,
            "invoice_number": invoice.invoice_number,
            "payment_type": payment_type,
            "vendor": invoice.vendor,
            "amount": str(invoice.amount) if invoice.amount else None,
            "vs": invoice.vs,
        }

        # Update session results - move transaction from unmatched to matched
        if session.results_json:
            results = session.results_json.copy()
            unmatched = results.get("unmatched", [])
            matched = results.get("matched", [])

            # Remove the transaction from unmatched
            for i, trans in enumerate(unmatched):
                if trans.get("id") == transaction_id:
                    unmatched.pop(i)
                    break

            # Add to matched with manual match info
            matched.append({
                "transaction": transaction_data,
                "invoice": invoice_data,
                "confidence": 1.0,
                "confidence_pct": 100,
                "status": "OK",
                "strategy_scores": {"ManualMatch": 1.0},
            })

            results["unmatched"] = unmatched
            results["matched"] = matched

            session.results_json = results
            session.unmatched_count = len(unmatched)
            session.matched_count = len([m for m in matched if m.get("status") == "OK"])
            flag_modified(session, "results_json")
            db.commit()

        return MatchWithPdfResponse(
            success=True,
            message="Transaction matched with uploaded invoice",
            gdrive_file_id=gdrive_file_id,
            invoice=invoice_data,
        )

    finally:
        # Clean up temp file
        tmp_path.unlink(missing_ok=True)


# ===== Month-Based Endpoints =====

def run_monthly_task(
    year_month: str,
    fio_token: str,
    invoice_dir: Path | None,
    prev_month_invoice_dir: Path | None,
    db_url: str
):
    """Background task to run monthly reconciliation."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        service = ReconcileService(db)
        month = service.get_month(year_month)
        if month:
            service.run_monthly_reconciliation(
                month, fio_token, invoice_dir, prev_month_invoice_dir
            )
    finally:
        db.close()


@router.get("/months", response_model=list[MonthListItem])
def list_months(db: Session = Depends(get_db)):
    """List all months with reconciliation data."""
    service = ReconcileService(db)
    months = service.list_months()
    return [
        MonthListItem(
            year_month=m.year_month,
            status=m.status,
            matched_count=m.matched_count,
            unmatched_count=m.unmatched_count,
            last_synced_at=m.last_synced_at,
            gdrive_folder_id=m.gdrive_folder_id,
            gdrive_folder_name=m.gdrive_folder_name,
        )
        for m in months
    ]


@router.post("/months/{year_month}/set-folder")
def set_month_folder(
    year_month: str,
    request: SetFolderRequest,
    db: Session = Depends(get_db)
):
    """Set Google Drive folder for a month."""
    # Treat empty strings as clearing the folder
    folder_id = request.folder_id if request.folder_id else None
    folder_name = request.folder_name if request.folder_name else None

    # Get or create month record
    month = db.query(MonthlyReconciliation).filter(
        MonthlyReconciliation.year_month == year_month
    ).first()

    if not month:
        month = MonthlyReconciliation(
            year_month=year_month,
            gdrive_folder_id=folder_id,
            gdrive_folder_name=folder_name,
        )
        db.add(month)
    else:
        month.gdrive_folder_id = folder_id
        month.gdrive_folder_name = folder_name

    db.commit()
    return {"success": True, "year_month": year_month, "folder_id": folder_id}


@router.post("/months/{year_month}/sync", response_model=ReconcileResponse)
def sync_month(
    year_month: str,
    request: MonthlyReconcileRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Sync reconciliation for a specific month."""
    print(f"[SYNC] {year_month}: folder={request.gdrive_folder_id}, prev_folder={request.prev_month_gdrive_folder_id}")

    # Validate year_month format
    import re
    if not re.match(r"^\d{4}-\d{2}$", year_month):
        raise HTTPException(status_code=400, detail="Invalid year_month format. Use YYYY-MM")

    service = ReconcileService(db)

    # Get or create monthly record
    month = service.get_or_create_month(year_month, request.gdrive_folder_id)

    # Determine invoice directory for current month
    invoice_dir = None
    if request.invoice_dir:
        invoice_dir = Path(request.invoice_dir)
        if not invoice_dir.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Invoice directory not found: {request.invoice_dir}"
            )
    elif request.gdrive_folder_id:
        if _gdrive_service.is_available:
            if not _gdrive_service._credentials:
                raise HTTPException(
                    status_code=401,
                    detail="Not authenticated with Google Drive. Please connect first."
                )
            try:
                invoice_dir, downloaded_files, _ = _gdrive_service.download_pdfs(request.gdrive_folder_id, db, force_refresh=True)
                # Don't error if no files - might all be late payments
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to download from Google Drive: {e}"
                )

    # Determine invoice directory for previous month (for late payments)
    prev_month_invoice_dir = None
    if request.prev_month_invoice_dir:
        prev_month_invoice_dir = Path(request.prev_month_invoice_dir)
    elif request.prev_month_gdrive_folder_id:
        if _gdrive_service.is_available and _gdrive_service._credentials:
            try:
                prev_month_invoice_dir, prev_files, _ = _gdrive_service.download_pdfs(
                    request.prev_month_gdrive_folder_id, db, force_refresh=True
                )
                print(f"[SYNC] Downloaded {len(prev_files)} files from prev month folder")
            except Exception as e:
                print(f"[SYNC] Failed to download prev month: {e}")

    print(f"[SYNC] invoice_dir={invoice_dir}, prev_month_invoice_dir={prev_month_invoice_dir}")

    # Run reconciliation in background
    from web.database.connection import DATABASE_URL
    background_tasks.add_task(
        run_monthly_task,
        year_month,
        request.fio_token,
        invoice_dir,
        prev_month_invoice_dir,
        DATABASE_URL
    )

    return ReconcileResponse(
        session_id=0,  # Not used for months
        status="processing",
        message=f"Reconciliation started for {year_month}"
    )


@router.get("/months/{year_month}", response_model=MonthResponse)
def get_month(year_month: str, db: Session = Depends(get_db)):
    """Get reconciliation data for a specific month."""
    service = ReconcileService(db)
    month = service.get_month(year_month)

    if not month:
        raise HTTPException(status_code=404, detail="Month not found")

    results = service.get_month_results(month)

    return MonthResponse(
        year_month=month.year_month,
        status=month.status,
        last_synced_at=month.last_synced_at,
        created_at=month.created_at,
        matched_count=month.matched_count,
        unmatched_count=month.unmatched_count,
        review_count=month.review_count,
        known_count=month.known_count,
        fee_count=month.fee_count,
        income_count=month.income_count,
        matched=results.get("matched", []),
        unmatched=results.get("unmatched", []),
        known=results.get("known", []),
        fees=results.get("fees", []),
        income=results.get("income", []),
        unmatched_invoices=results.get("unmatched_invoices", []),
        error_message=month.error_message,
    )


@router.post("/months/{year_month}/mark-known")
def mark_as_known_monthly(
    year_month: str,
    request: MarkKnownRequest,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Mark a transaction as known for a specific month."""
    reconcile_service = ReconcileService(db)
    known_service = KnownTransactionService(db)

    month = reconcile_service.get_month(year_month)
    if not month:
        raise HTTPException(status_code=404, detail="Month not found")

    # Create the known transaction rule
    rule_data = KnownTransactionCreate(
        rule_type=request.rule_type,
        reason=request.reason,
        vendor_pattern=request.vendor_pattern,
        note_pattern=request.note_pattern,
        amount=request.amount,
        amount_min=request.amount_min,
        amount_max=request.amount_max,
        counter_account=request.counter_account,
    )

    rule = known_service.create(rule_data)

    # Update month results to move ALL matching transactions to known
    if month.results_json:
        results = month.results_json.copy()

        unmatched = results.get("unmatched", [])
        known = results.get("known", [])

        new_unmatched = []
        matched_count = 0

        for trans in unmatched:
            matches = False

            if request.rule_type == "note" and request.note_pattern:
                import re
                try:
                    pattern = re.compile(request.note_pattern, re.IGNORECASE)
                    note = trans.get("note") or ""
                    matches = bool(pattern.search(note))
                except re.error:
                    pass
            elif request.rule_type == "vendor" and request.vendor_pattern:
                import re
                try:
                    pattern = re.compile(request.vendor_pattern, re.IGNORECASE)
                    text = f"{trans.get('counter_name', '')} {trans.get('note', '')}"
                    matches = bool(pattern.search(text))
                except re.error:
                    pass
            elif request.rule_type == "exact":
                matches = trans.get("id") == request.transaction_id

            if matches:
                trans["rule_reason"] = request.reason
                known.append(trans)
                matched_count += 1
            else:
                new_unmatched.append(trans)

        results["unmatched"] = new_unmatched
        results["known"] = known

        month.results_json = results
        month.unmatched_count = len(new_unmatched)
        month.known_count = len(known)
        flag_modified(month, "results_json")
        db.commit()

    return {
        "success": True,
        "rule_id": rule.id,
        "matched_count": matched_count,
        "message": f"Marked {matched_count} transaction(s) as known"
    }


@router.post("/months/{year_month}/match-with-pdf", response_model=MatchWithPdfResponse)
async def match_with_pdf_monthly(
    year_month: str,
    transaction_id: str = Form(...),
    file: UploadFile = File(...),
    force: bool = Form(False),
    db: Session = Depends(get_db)
):
    """Match an unmatched transaction with an uploaded PDF invoice for a month.

    If invoice amount doesn't match transaction amount, returns error unless force=true.
    """
    reconcile_service = ReconcileService(db)
    month = reconcile_service.get_month(year_month)

    if not month:
        raise HTTPException(status_code=404, detail="Month not found")

    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    content = await file.read()

    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        transaction_data = None
        if month.results_json:
            unmatched = month.results_json.get("unmatched", [])
            for trans in unmatched:
                if trans.get("id") == transaction_id:
                    transaction_data = trans
                    break

        if not transaction_data:
            raise HTTPException(status_code=404, detail="Transaction not found in unmatched list")

        payment_type = transaction_data.get("transaction_type", "unknown")

        invoice = parse_uploaded_pdf(tmp_path)
        if not invoice:
            raise HTTPException(status_code=400, detail="Could not extract data from PDF.")

        # Validate amount match
        amount_warning = None
        if invoice.amount is not None:
            transaction_amount = abs(Decimal(str(transaction_data.get("amount", 0))))
            invoice_amount = abs(invoice.amount)
            # Allow 5 cent tolerance
            if abs(transaction_amount - invoice_amount) > Decimal("0.05"):
                if not force:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Amount mismatch: invoice shows {invoice_amount} EUR but transaction is {transaction_amount} EUR. "
                               f"Upload the correct file or confirm to force match."
                    )
                else:
                    amount_warning = f"Forced match with amount mismatch: invoice {invoice_amount} EUR vs transaction {transaction_amount} EUR"

        invoice_date_str = str(invoice.invoice_date) if invoice.invoice_date else "unknown"
        vendor_slug = (invoice.vendor or "unknown").lower().replace(" ", "-")[:20]

        sequence_num = 1
        gdrive_file_id = None
        gdrive_filename = f"{invoice_date_str}-{sequence_num:03d}_{payment_type}_{vendor_slug}.pdf"

        if month.gdrive_folder_id and _gdrive_service._credentials:
            try:
                existing_files = _gdrive_service.list_files_in_folder(month.gdrive_folder_id)
                date_prefix = f"{invoice_date_str}-"

                for fname in existing_files:
                    if fname.startswith(date_prefix):
                        parts = fname.split("_")
                        if parts:
                            try:
                                seq = int(parts[0].split("-")[-1])
                                if seq >= sequence_num:
                                    sequence_num = seq + 1
                            except (ValueError, IndexError):
                                pass

                gdrive_filename = f"{invoice_date_str}-{sequence_num:03d}_{payment_type}_{vendor_slug}.pdf"
                gdrive_file_id = _gdrive_service.upload_pdf(
                    month.gdrive_folder_id,
                    gdrive_filename,
                    content
                )
            except Exception:
                pass

        invoice_data = {
            "file_path": gdrive_filename if gdrive_file_id else str(invoice.file_path),
            "filename": gdrive_filename,
            "invoice_date": str(invoice.invoice_date) if invoice.invoice_date else None,
            "invoice_number": invoice.invoice_number,
            "payment_type": payment_type,
            "vendor": invoice.vendor,
            "amount": str(invoice.amount) if invoice.amount else None,
            "vs": invoice.vs,
        }

        if month.results_json:
            results = month.results_json.copy()
            unmatched = results.get("unmatched", [])
            matched = results.get("matched", [])

            for i, trans in enumerate(unmatched):
                if trans.get("id") == transaction_id:
                    unmatched.pop(i)
                    break

            matched.append({
                "transaction": transaction_data,
                "invoice": invoice_data,
                "confidence": 1.0,
                "confidence_pct": 100,
                "status": "OK",
                "strategy_scores": {"ManualMatch": 1.0},
            })

            results["unmatched"] = unmatched
            results["matched"] = matched

            month.results_json = results
            month.unmatched_count = len(unmatched)
            month.matched_count = len([m for m in matched if m.get("status") == "OK"])
            flag_modified(month, "results_json")
            db.commit()

        return MatchWithPdfResponse(
            success=True,
            message="Transaction matched with uploaded invoice",
            gdrive_file_id=gdrive_file_id,
            invoice=invoice_data,
            warning=amount_warning,
        )

    finally:
        tmp_path.unlink(missing_ok=True)


@router.get("/months/{year_month}/download-invoices")
async def download_matched_invoices(
    year_month: str,
    db: Session = Depends(get_db)
):
    """Download all invoices from the month's Google Drive folder as a zip file.

    Downloads ALL PDFs from the folder (for VAT purposes), not just matched ones.
    This ensures invoices are included based on their folder location (VAT date),
    regardless of which month the payment was made.
    """
    reconcile_service = ReconcileService(db)
    month = reconcile_service.get_month(year_month)

    if not month:
        raise HTTPException(status_code=404, detail="Month not found")

    if not month.gdrive_folder_id:
        raise HTTPException(status_code=400, detail="No Google Drive folder set for this month")

    if not _gdrive_service._credentials:
        raise HTTPException(status_code=401, detail="Not authenticated with Google Drive")

    try:
        # List all PDF files in the folder
        files = _gdrive_service.list_pdfs(month.gdrive_folder_id)

        if not files:
            raise HTTPException(status_code=400, detail="No PDF files found in the folder")

        # Create list of (file_id, filename) tuples
        files_to_download = [(f["id"], f["name"]) for f in files]

        zip_content = _gdrive_service.download_files_as_zip(files_to_download, db)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create zip: {str(e)}")

    return Response(
        content=zip_content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="invoices-{year_month}.zip"'
        }
    )


@router.get("/months/{year_month}/invoices")
def get_month_invoices(
    year_month: str,
    db: Session = Depends(get_db)
):
    """Get all invoices for a month with their payment status.

    Returns invoices from this month's folder, indicating whether they've been paid
    and in which month the payment occurred.
    """
    # Get all invoice payments for this month (invoices stored in this month's folder)
    payments = db.query(InvoicePayment).filter(
        InvoicePayment.invoice_month == year_month
    ).all()

    invoices = []
    for p in payments:
        invoices.append({
            "gdrive_file_id": p.gdrive_file_id,
            "filename": p.filename,
            "vendor": p.vendor,
            "amount": str(p.amount) if p.amount else None,
            "status": "paid" if p.paid_month else "unpaid",
            "paid_month": p.paid_month,
            "transaction_id": p.transaction_id,
        })

    return {"invoices": invoices, "total": len(invoices)}


@router.post("/months/{year_month}/upload-invoice")
async def upload_invoice_to_month(
    year_month: str,
    file: UploadFile = File(...),
    invoice_date: str = Form(...),  # YYYY-MM-DD format for invoice/VAT date
    db: Session = Depends(get_db)
):
    """Upload a new invoice to a month's Google Drive folder.

    Args:
        year_month: The month to upload to (YYYY-MM format)
        file: PDF file to upload
        invoice_date: The invoice/VAT date (used for filename prefix)
    """
    from datetime import datetime

    # Validate year_month format
    try:
        y, m = map(int, year_month.split("-"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid year_month format. Use YYYY-MM")

    # Parse invoice_date
    try:
        inv_date = datetime.strptime(invoice_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid invoice_date format. Use YYYY-MM-DD")

    # Get month record
    month = db.query(MonthlyReconciliation).filter(
        MonthlyReconciliation.year_month == year_month
    ).first()

    if not month:
        raise HTTPException(status_code=404, detail=f"Month {year_month} not found")

    # Get folder ID - either from month record or auto-resolve from parent
    folder_id = month.gdrive_folder_id

    if not folder_id:
        # Try to auto-resolve from parent folder setting
        parent_setting = db.query(AppSettings).filter(
            AppSettings.key == "invoice_parent_folder_id"
        ).first()

        if parent_setting and parent_setting.value:
            subfolder_name = f"{y}{m:02d}"
            subfolder = _gdrive_service.find_subfolder(parent_setting.value, subfolder_name)
            if subfolder:
                folder_id = subfolder.id
                month.gdrive_folder_id = folder_id
                month.gdrive_folder_name = subfolder.name
                db.commit()

    if not folder_id:
        raise HTTPException(
            status_code=400,
            detail="No Google Drive folder configured for this month"
        )

    if not _gdrive_service.is_available:
        raise HTTPException(status_code=503, detail="Google Drive not available")

    if not _gdrive_service._credentials:
        raise HTTPException(status_code=401, detail="Not authenticated with Google Drive")

    # Read file content
    content = await file.read()

    # Create filename with date prefix: YYYY-MM-DD_originalname.pdf
    original_filename = file.filename or "invoice.pdf"
    # Remove .pdf extension if present, then add it back
    base_name = original_filename[:-4] if original_filename.lower().endswith(".pdf") else original_filename
    new_filename = f"{inv_date.strftime('%Y-%m-%d')}_{base_name}.pdf"

    try:
        # Upload to Google Drive
        gdrive_file_id = _gdrive_service.upload_pdf(folder_id, new_filename, content)

        # Cache the PDF
        from web.database.models import PDFCache
        cache_entry = PDFCache(
            gdrive_file_id=gdrive_file_id,
            filename=new_filename,
            content=content,
            file_size=len(content),
        )
        db.add(cache_entry)

        # Create invoice payment record (unpaid initially)
        payment = InvoicePayment(
            invoice_month=year_month,
            gdrive_file_id=gdrive_file_id,
            filename=new_filename,
            paid_month=None,
            transaction_id=None,
            amount=None,
            vendor=None,
        )
        db.add(payment)
        db.commit()

        return {
            "success": True,
            "gdrive_file_id": gdrive_file_id,
            "filename": new_filename,
            "message": f"Invoice uploaded to {year_month}"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload: {str(e)}")


# ===== Settings Endpoints =====

@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    """Get all app settings."""
    settings = db.query(AppSettings).all()
    return {s.key: s.value for s in settings}


@router.get("/settings/{key}")
def get_setting(key: str, db: Session = Depends(get_db)):
    """Get a specific setting."""
    setting = db.query(AppSettings).filter(AppSettings.key == key).first()
    return {"key": key, "value": setting.value if setting else None}


@router.put("/settings/{key}")
def set_setting(key: str, value: str = "", db: Session = Depends(get_db)):
    """Set a setting value."""
    setting = db.query(AppSettings).filter(AppSettings.key == key).first()
    if setting:
        setting.value = value if value else None
    else:
        setting = AppSettings(key=key, value=value if value else None)
        db.add(setting)
    db.commit()
    return {"key": key, "value": setting.value}
