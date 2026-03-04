#!/usr/bin/env python3
"""
Bank Statement to Invoice Reconciliation Utility

Automatically matches bank transactions with invoice PDFs based on:
- Amount (40% weight)
- Vendor name (25% weight)
- Date proximity (20% weight)
- Variable Symbol (15% weight)

Usage:
    # From CSV file
    python reconcile.py statement.csv invoices/ -o report.html

    # From Fio Bank API
    python reconcile.py --api --from 2026-02-01 --to 2026-02-28 invoices/ -o report.html
"""

import argparse
import io
import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding for Unicode output
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from parsers import parse_bank_statement, parse_invoices, fetch_transactions_from_api, get_token_from_env
from matching import Matcher
from reports import Reporter, HTMLReporter


def parse_date(date_str: str):
    """Parse date string in YYYY-MM-DD format."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date format: {date_str}. Use YYYY-MM-DD")


def main():
    parser = argparse.ArgumentParser(
        description="Reconcile bank statement with invoice PDFs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # From CSV file
  python reconcile.py statement.csv invoices/ -o report.html

  # From Fio Bank API (token from environment)
  export FIO_API_TOKEN=your_token_here
  python reconcile.py --api --from 2026-02-01 --to 2026-02-28 invoices/ -o report.html

  # From Fio Bank API (token as argument)
  python reconcile.py --api --token YOUR_TOKEN --from 2026-02-01 --to 2026-02-28 invoices/
        """
    )

    # Input source (CSV or API)
    parser.add_argument(
        "csv_file",
        type=Path,
        nargs="?",
        help="Path to bank statement CSV file (not needed with --api)"
    )
    parser.add_argument(
        "invoice_dir",
        type=Path,
        help="Directory containing invoice PDF files"
    )

    # API options
    api_group = parser.add_argument_group("Fio Bank API options")
    api_group.add_argument(
        "--api",
        action="store_true",
        help="Fetch transactions from Fio Bank API instead of CSV file"
    )
    api_group.add_argument(
        "--token",
        type=str,
        help="Fio Bank API token (or set FIO_API_TOKEN environment variable)"
    )
    api_group.add_argument(
        "--from",
        dest="from_date",
        type=parse_date,
        help="Start date for API fetch (YYYY-MM-DD)"
    )
    api_group.add_argument(
        "--to",
        dest="to_date",
        type=parse_date,
        help="End date for API fetch (YYYY-MM-DD)"
    )

    # Output options
    output_group = parser.add_argument_group("Output options")
    output_group.add_argument(
        "-o", "--output",
        type=Path,
        help="Output file for report (optional, prints to stdout if not specified)"
    )
    output_group.add_argument(
        "--html",
        action="store_true",
        help="Generate HTML report (auto-detected if output ends with .html)"
    )
    output_group.add_argument(
        "--open",
        action="store_true",
        help="Open HTML report in browser after generation"
    )

    args = parser.parse_args()

    # Validate inputs based on mode
    if args.api:
        # API mode
        token = args.token or get_token_from_env()
        if not token:
            print("Error: Fio API token required. Use --token or set FIO_API_TOKEN env var", file=sys.stderr)
            sys.exit(1)

        if not args.from_date or not args.to_date:
            print("Error: --from and --to dates required for API mode", file=sys.stderr)
            sys.exit(1)

        if args.from_date > args.to_date:
            print("Error: --from date must be before --to date", file=sys.stderr)
            sys.exit(1)

    else:
        # CSV mode
        if not args.csv_file:
            print("Error: CSV file required (or use --api for API mode)", file=sys.stderr)
            sys.exit(1)

        if not args.csv_file.exists():
            print(f"Error: CSV file not found: {args.csv_file}", file=sys.stderr)
            sys.exit(1)

    if not args.invoice_dir.exists():
        print(f"Error: Invoice directory not found: {args.invoice_dir}", file=sys.stderr)
        sys.exit(1)

    # Auto-detect HTML from output extension
    use_html = args.html
    if args.output and args.output.suffix.lower() in ('.html', '.htm'):
        use_html = True

    # Get transactions
    if args.api:
        print(f"Fetching transactions from Fio Bank API...")
        print(f"  Period: {args.from_date} to {args.to_date}")
        try:
            transactions = fetch_transactions_from_api(token, args.from_date, args.to_date)
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error fetching from API: {e}", file=sys.stderr)
            sys.exit(1)
        source_desc = f"Fio API ({args.from_date} to {args.to_date})"
    else:
        print(f"Parsing bank statement: {args.csv_file}")
        transactions = parse_bank_statement(args.csv_file)
        source_desc = str(args.csv_file)

    print(f"  Found {len(transactions)} transactions")

    fee_count = sum(1 for t in transactions if t.is_fee)
    print(f"  ({fee_count} fee transactions will be excluded)")

    print(f"\nParsing invoices from: {args.invoice_dir}")
    invoices = parse_invoices(args.invoice_dir)
    print(f"  Found {len(invoices)} invoices")

    # Run matching
    print("\nRunning reconciliation...")
    matcher = Matcher()
    matched, unmatched_trans, unmatched_inv = matcher.match_all(transactions, invoices)

    # Generate report
    if use_html:
        reporter = HTMLReporter()
        report = reporter.generate_report(
            matched, unmatched_trans, unmatched_inv,
            csv_file=source_desc,
            invoice_dir=str(args.invoice_dir)
        )
        output_path = args.output or Path("report.html")
        reporter.save_report(report, output_path)
        print(f"\nHTML report saved to: {output_path}")

        if args.open:
            webbrowser.open(f"file://{output_path.resolve()}")
    else:
        reporter = Reporter()
        report = reporter.generate_report(matched, unmatched_trans, unmatched_inv)

        if args.output:
            reporter.save_report(report, args.output)
            print(f"\nReport saved to: {args.output}")
        else:
            print("\n")
            print(report)


if __name__ == "__main__":
    main()
