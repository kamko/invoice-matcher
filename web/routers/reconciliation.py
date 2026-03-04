"""Router for reconciliation endpoints."""

import tempfile
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form
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
)
from parsers.pdf_parser import parse_uploaded_pdf
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
                invoice_dir, downloaded_files = _gdrive_service.download_pdfs(request.gdrive_folder_id)
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
        )
        for m in months
    ]


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
                invoice_dir, downloaded_files = _gdrive_service.download_pdfs(request.gdrive_folder_id)
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
                prev_month_invoice_dir, prev_files = _gdrive_service.download_pdfs(
                    request.prev_month_gdrive_folder_id
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
    db: Session = Depends(get_db)
):
    """Match an unmatched transaction with an uploaded PDF invoice for a month."""
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
        )

    finally:
        tmp_path.unlink(missing_ok=True)
