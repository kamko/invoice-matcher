#!/usr/bin/env python3
"""Import existing data after v2 migration.

This script:
1. Fetches 2026 transactions from Fio API
2. Imports invoices from PDF cache (already downloaded)
3. Runs auto-matching

Usage:
    uv run python import_data.py --fio-token YOUR_FIO_TOKEN
"""

import argparse
import tempfile
from datetime import datetime, date, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from web.database.connection import SessionLocal
from web.database.models import Transaction, Invoice, PDFCache, AppSettings
from web.services.matching_service import MatchingService
from web.services.known_trans_service import KnownTransactionService
from parsers.fio_api import fetch_transactions_from_api
from parsers.pdf_parser import parse_uploaded_pdf


def get_fio_token(db: Session) -> str | None:
    """Get Fio token from database settings."""
    setting = db.query(AppSettings).filter(AppSettings.key == 'fio_token').first()
    return setting.value if setting else None


def import_transactions(db: Session, fio_token: str, from_date: date, to_date: date):
    """Import transactions from Fio API."""
    print(f"\nImporting transactions from {from_date} to {to_date}...")

    try:
        raw_transactions = fetch_transactions_from_api(
            token=fio_token.strip(),
            from_date=from_date,
            to_date=to_date,
        )
    except Exception as e:
        print(f"Error fetching from Fio: {e}")
        return 0

    matching = MatchingService(db)
    known_service = KnownTransactionService(db)

    new_count = 0
    existing_count = 0
    known_count = 0

    for raw in raw_transactions:
        # Check if exists
        existing = db.query(Transaction).filter(Transaction.id == raw.id).first()
        if existing:
            existing_count += 1
            continue

        # Classify type
        trans_type = 'expense'
        if raw.is_fee:
            trans_type = 'fee'
        elif raw.amount > 0:
            trans_type = 'income'

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
            fetched_at=datetime.now(timezone.utc),
        )

        # Check known rules
        rule = known_service.match_transaction(raw)
        if rule:
            transaction.status = 'known'
            transaction.known_rule_id = rule.id
            known_count += 1

        db.add(transaction)
        new_count += 1

    db.commit()
    print(f"  Fetched: {len(raw_transactions)}, New: {new_count}, Existing: {existing_count}, Known: {known_count}")
    return new_count


def import_invoices_from_cache(db: Session):
    """Import invoices from PDF cache."""
    print("\nImporting invoices from PDF cache...")

    cached_pdfs = db.query(PDFCache).all()
    print(f"  Found {len(cached_pdfs)} cached PDFs")

    imported = 0
    skipped = 0

    for cache in cached_pdfs:
        # Check if already imported
        existing = db.query(Invoice).filter(
            Invoice.gdrive_file_id == cache.gdrive_file_id,
            Invoice.receipt_index == 0
        ).first()

        if existing:
            skipped += 1
            continue

        # Parse the cached PDF
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                tmp.write(cache.content)
                tmp_path = Path(tmp.name)

            parsed = parse_uploaded_pdf(tmp_path)
            tmp_path.unlink(missing_ok=True)

            # parse_uploaded_pdf can return None if parsing fails
            if parsed is None:
                print(f"    Skipping {cache.filename}: PDF parsing returned None")
                continue

            # Create invoice - parse_uploaded_pdf returns an Invoice object, not a dict
            invoice = Invoice(
                gdrive_file_id=cache.gdrive_file_id,
                receipt_index=0,
                filename=cache.filename,
                vendor=parsed.vendor,
                amount=parsed.amount,
                invoice_date=parsed.invoice_date,
                payment_type=parsed.payment_type or 'card',
                vs=parsed.vs,
                iban=getattr(parsed, 'iban', None),
                is_credit_note=getattr(parsed, 'is_credit_note', False),
                status='unmatched',
                created_at=datetime.now(timezone.utc),
            )

            db.add(invoice)
            db.commit()  # Commit each invoice individually to avoid losing progress
            imported += 1

        except Exception as e:
            db.rollback()  # Rollback on error
            print(f"    Error parsing {cache.filename}: {e}")
            continue
    print(f"  Imported: {imported}, Skipped (existing): {skipped}")
    return imported


def run_auto_matching(db: Session):
    """Run auto-matching on all unmatched invoices."""
    print("\nRunning auto-matching...")

    matching = MatchingService(db)
    results = matching.run_auto_matching()

    print(f"  VS matches: {results['tier1_vs']}")
    print(f"  IBAN matches: {results['tier1_iban']}")
    print(f"  Vendor alias matches: {results['tier2_alias']}")
    print(f"  Total: {sum(results.values())}")


def main():
    parser = argparse.ArgumentParser(description='Import data after v2 migration')
    parser.add_argument('--fio-token', help='Fio API token (optional, will use saved token)')
    parser.add_argument('--from-date', default='2026-01-01', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--to-date', default=datetime.now().strftime('%Y-%m-%d'), help='End date (YYYY-MM-DD)')
    parser.add_argument('--invoices-only', action='store_true', help='Only import invoices from cache (skip Fio)')
    args = parser.parse_args()

    print("=" * 60)
    print("Invoice Matcher v2 - Data Import")
    print("=" * 60)

    db = SessionLocal()

    try:
        if not args.invoices_only:
            # Get Fio token
            fio_token = args.fio_token or get_fio_token(db)
            if not fio_token:
                print("Error: No Fio token provided. Use --fio-token or configure in settings.")
                print("       Or use --invoices-only to import only invoices from cache.")
                return

            from_date = datetime.strptime(args.from_date, '%Y-%m-%d').date()
            to_date = datetime.strptime(args.to_date, '%Y-%m-%d').date()

            # Import transactions
            import_transactions(db, fio_token, from_date, to_date)

        # Import invoices from cache
        import_invoices_from_cache(db)

        # Run auto-matching (only useful if we have both invoices and transactions)
        if not args.invoices_only:
            run_auto_matching(db)

        # Summary
        print("\n" + "=" * 60)
        print("Import Summary")
        print("=" * 60)

        trans_count = db.query(Transaction).count()
        inv_count = db.query(Invoice).count()
        matched_count = db.query(Invoice).filter(Invoice.status == 'matched').count()

        print(f"  Total transactions: {trans_count}")
        print(f"  Total invoices: {inv_count}")
        print(f"  Matched: {matched_count}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
