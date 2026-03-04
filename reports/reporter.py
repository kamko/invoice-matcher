"""Report generation for reconciliation results."""

from pathlib import Path
from typing import List, Optional

from tabulate import tabulate

from matching.matcher import MatchResult
from models.invoice import Invoice
from models.transaction import Transaction
from parsers.csv_parser import extract_vendor_from_note


class Reporter:
    """Generates reconciliation reports."""

    def generate_report(
        self,
        matched: List[MatchResult],
        unmatched_transactions: List[Transaction],
        unmatched_invoices: List[Invoice],
    ) -> str:
        """
        Generate a full text report.

        Args:
            matched: List of match results
            unmatched_transactions: Transactions without invoices
            unmatched_invoices: Invoices without matching transactions

        Returns:
            Formatted report string
        """
        lines = []

        # Header
        lines.append("=" * 80)
        lines.append("RECONCILIATION REPORT")
        lines.append("=" * 80)
        lines.append("")

        # Summary
        high_confidence = sum(1 for m in matched if m.confidence >= 0.70)
        needs_review = sum(1 for m in matched if 0.30 <= m.confidence < 0.70)

        lines.append("SUMMARY:")
        lines.append(f"  Total Matched:          {len(matched)}")
        lines.append(f"    - High Confidence:    {high_confidence}")
        lines.append(f"    - Needs Review:       {needs_review}")
        lines.append(f"  Unmatched Transactions: {len(unmatched_transactions)}")
        lines.append(f"  Unmatched Invoices:     {len(unmatched_invoices)}")
        lines.append("")

        # Matched transactions
        if matched:
            lines.append("-" * 80)
            lines.append("MATCHED TRANSACTIONS")
            lines.append("-" * 80)

            table_data = []
            for m in sorted(matched, key=lambda x: x.transaction.date):
                vendor = extract_vendor_from_note(m.transaction.note)[:20]
                invoice_name = m.invoice.filename if m.invoice else "N/A"
                table_data.append([
                    m.transaction.date.strftime("%Y-%m-%d"),
                    f"{m.transaction.abs_amount:,.2f}",
                    vendor,
                    invoice_name,
                    f"{m.confidence_pct}%",
                    m.status
                ])

            headers = ["Date", "Amount", "Vendor", "Invoice", "Conf.", "Status"]
            lines.append(tabulate(table_data, headers=headers, tablefmt="simple"))
            lines.append("")

        # Unmatched transactions
        if unmatched_transactions:
            lines.append("-" * 80)
            lines.append("UNMATCHED TRANSACTIONS (Missing invoices)")
            lines.append("-" * 80)

            table_data = []
            for t in sorted(unmatched_transactions, key=lambda x: x.date):
                vendor = extract_vendor_from_note(t.note)[:30]
                table_data.append([
                    t.date.strftime("%Y-%m-%d"),
                    f"{t.abs_amount:,.2f}",
                    t.transaction_type.upper(),
                    vendor,
                    t.vs or "-"
                ])

            headers = ["Date", "Amount", "Type", "Vendor/Note", "VS"]
            lines.append(tabulate(table_data, headers=headers, tablefmt="simple"))
            lines.append("")

        # Unmatched invoices
        if unmatched_invoices:
            lines.append("-" * 80)
            lines.append("UNMATCHED INVOICES (Payment pending)")
            lines.append("-" * 80)

            table_data = []
            for inv in sorted(unmatched_invoices, key=lambda x: x.invoice_date):
                amount_str = f"{inv.amount:,.2f}" if inv.amount else "N/A"
                table_data.append([
                    inv.invoice_date.strftime("%Y-%m-%d"),
                    amount_str,
                    inv.payment_type.upper(),
                    inv.vendor,
                    inv.filename
                ])

            headers = ["Date", "Amount", "Type", "Vendor", "File"]
            lines.append(tabulate(table_data, headers=headers, tablefmt="simple"))
            lines.append("")

        lines.append("=" * 80)
        lines.append("END OF REPORT")
        lines.append("=" * 80)

        return "\n".join(lines)

    def save_report(self, report: str, output_path: Path) -> None:
        """Save report to file."""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)
