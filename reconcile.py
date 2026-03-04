#!/usr/bin/env python3
"""
Bank Statement to Invoice Reconciliation Utility

Automatically matches bank transactions with invoice PDFs based on:
- Amount (40% weight)
- Vendor name (25% weight)
- Date proximity (20% weight)
- Variable Symbol (15% weight)

Usage:
    python reconcile.py <bank_statement.csv> <invoice_directory> [-o output.txt]
    python reconcile.py <bank_statement.csv> <invoice_directory> --html -o report.html
"""

import argparse
import io
import sys
import webbrowser
from pathlib import Path

# Fix Windows console encoding for Unicode output
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from parsers import parse_bank_statement, parse_invoices
from matching import Matcher
from reports import Reporter, HTMLReporter


def main():
    parser = argparse.ArgumentParser(
        description="Reconcile bank statement with invoice PDFs"
    )
    parser.add_argument(
        "csv_file",
        type=Path,
        help="Path to bank statement CSV file"
    )
    parser.add_argument(
        "invoice_dir",
        type=Path,
        help="Directory containing invoice PDF files"
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output file for report (optional, prints to stdout if not specified)"
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Generate HTML report (auto-detected if output ends with .html)"
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open HTML report in browser after generation"
    )

    args = parser.parse_args()

    # Validate inputs
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

    # Parse inputs
    print(f"Parsing bank statement: {args.csv_file}")
    transactions = parse_bank_statement(args.csv_file)
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
            csv_file=str(args.csv_file),
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
