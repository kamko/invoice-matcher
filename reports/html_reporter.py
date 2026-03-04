"""HTML report generation for reconciliation results."""

from datetime import datetime
from pathlib import Path
from typing import List

from matching.matcher import MatchResult
from models.invoice import Invoice
from models.transaction import Transaction
from parsers.csv_parser import extract_vendor_from_note


class HTMLReporter:
    """Generates HTML reconciliation reports."""

    def generate_report(
        self,
        matched: List[MatchResult],
        unmatched_transactions: List[Transaction],
        unmatched_invoices: List[Invoice],
        csv_file: str = "",
        invoice_dir: str = "",
    ) -> str:
        """Generate a styled HTML report."""

        # Calculate summary stats
        high_confidence = sum(1 for m in matched if m.confidence >= 0.70)
        needs_review = sum(1 for m in matched if 0.30 <= m.confidence < 0.70)
        total_matched_amount = sum(m.transaction.abs_amount for m in matched)
        total_unmatched_amount = sum(t.abs_amount for t in unmatched_transactions)

        # Generate matched rows
        matched_rows = ""
        for m in sorted(matched, key=lambda x: x.transaction.date):
            vendor = extract_vendor_from_note(m.transaction.note)[:25]
            invoice_name = m.invoice.filename if m.invoice else "N/A"
            status_class = "status-ok" if m.status == "OK" else "status-review"
            conf_class = "conf-high" if m.confidence >= 0.70 else "conf-medium"

            matched_rows += f"""
            <tr>
                <td>{m.transaction.date.strftime("%Y-%m-%d")}</td>
                <td class="amount">{m.transaction.abs_amount:,.2f} EUR</td>
                <td>{vendor}</td>
                <td class="invoice-name">{invoice_name}</td>
                <td class="{conf_class}">{m.confidence_pct}%</td>
                <td class="{status_class}">{m.status}</td>
            </tr>"""

        # Generate unmatched transaction rows
        unmatched_trans_rows = ""
        for t in sorted(unmatched_transactions, key=lambda x: x.date):
            vendor = extract_vendor_from_note(t.note)[:35]
            type_class = "type-card" if t.is_card else "type-wire"

            unmatched_trans_rows += f"""
            <tr>
                <td>{t.date.strftime("%Y-%m-%d")}</td>
                <td class="amount">{t.abs_amount:,.2f} EUR</td>
                <td class="{type_class}">{t.transaction_type.upper()}</td>
                <td>{vendor}</td>
                <td class="vs">{t.vs or "-"}</td>
            </tr>"""

        # Generate unmatched invoice rows
        unmatched_inv_rows = ""
        for inv in sorted(unmatched_invoices, key=lambda x: x.invoice_date):
            amount_str = f"{inv.amount:,.2f} EUR" if inv.amount else "N/A"
            type_class = "type-card" if inv.is_card else "type-wire"

            unmatched_inv_rows += f"""
            <tr>
                <td>{inv.invoice_date.strftime("%Y-%m-%d")}</td>
                <td class="amount">{amount_str}</td>
                <td class="{type_class}">{inv.payment_type.upper()}</td>
                <td>{inv.vendor}</td>
                <td class="invoice-name">{inv.filename}</td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reconciliation Report</title>
    <style>
        :root {{
            --primary: #2563eb;
            --success: #16a34a;
            --warning: #d97706;
            --danger: #dc2626;
            --gray-50: #f9fafb;
            --gray-100: #f3f4f6;
            --gray-200: #e5e7eb;
            --gray-300: #d1d5db;
            --gray-600: #4b5563;
            --gray-800: #1f2937;
            --gray-900: #111827;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: var(--gray-50);
            color: var(--gray-800);
            line-height: 1.6;
            padding: 2rem;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}

        header {{
            background: white;
            border-radius: 12px;
            padding: 2rem;
            margin-bottom: 2rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}

        h1 {{
            color: var(--gray-900);
            font-size: 1.75rem;
            margin-bottom: 0.5rem;
        }}

        .subtitle {{
            color: var(--gray-600);
            font-size: 0.9rem;
        }}

        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}

        .stat-card {{
            background: white;
            border-radius: 12px;
            padding: 1.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}

        .stat-card.success {{
            border-left: 4px solid var(--success);
        }}

        .stat-card.warning {{
            border-left: 4px solid var(--warning);
        }}

        .stat-card.danger {{
            border-left: 4px solid var(--danger);
        }}

        .stat-card.info {{
            border-left: 4px solid var(--primary);
        }}

        .stat-value {{
            font-size: 2rem;
            font-weight: 700;
            color: var(--gray-900);
        }}

        .stat-label {{
            color: var(--gray-600);
            font-size: 0.875rem;
            margin-top: 0.25rem;
        }}

        section {{
            background: white;
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}

        h2 {{
            color: var(--gray-900);
            font-size: 1.25rem;
            margin-bottom: 1rem;
            padding-bottom: 0.75rem;
            border-bottom: 1px solid var(--gray-200);
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.875rem;
        }}

        th {{
            text-align: left;
            padding: 0.75rem 1rem;
            background: var(--gray-50);
            color: var(--gray-600);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.05em;
            border-bottom: 1px solid var(--gray-200);
        }}

        td {{
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--gray-100);
        }}

        tr:hover {{
            background: var(--gray-50);
        }}

        .amount {{
            font-family: 'SF Mono', Monaco, 'Courier New', monospace;
            text-align: right;
            font-weight: 500;
        }}

        .invoice-name {{
            font-family: 'SF Mono', Monaco, 'Courier New', monospace;
            font-size: 0.8rem;
            color: var(--gray-600);
        }}

        .vs {{
            font-family: 'SF Mono', Monaco, 'Courier New', monospace;
            color: var(--gray-600);
        }}

        .status-ok {{
            color: var(--success);
            font-weight: 600;
        }}

        .status-review {{
            color: var(--warning);
            font-weight: 600;
        }}

        .conf-high {{
            color: var(--success);
            font-weight: 600;
        }}

        .conf-medium {{
            color: var(--warning);
            font-weight: 600;
        }}

        .type-card {{
            background: #dbeafe;
            color: #1e40af;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
        }}

        .type-wire {{
            background: #dcfce7;
            color: #166534;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
        }}

        .empty-state {{
            text-align: center;
            padding: 2rem;
            color: var(--gray-600);
        }}

        footer {{
            text-align: center;
            color: var(--gray-600);
            font-size: 0.8rem;
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid var(--gray-200);
        }}

        @media print {{
            body {{
                background: white;
                padding: 0;
            }}
            .container {{
                max-width: 100%;
            }}
            section, header, .stat-card {{
                box-shadow: none;
                border: 1px solid var(--gray-200);
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Bank Reconciliation Report</h1>
            <p class="subtitle">Generated on {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
        </header>

        <div class="summary">
            <div class="stat-card success">
                <div class="stat-value">{high_confidence}</div>
                <div class="stat-label">High Confidence Matches</div>
            </div>
            <div class="stat-card warning">
                <div class="stat-value">{needs_review}</div>
                <div class="stat-label">Needs Review</div>
            </div>
            <div class="stat-card danger">
                <div class="stat-value">{len(unmatched_transactions)}</div>
                <div class="stat-label">Unmatched Transactions</div>
            </div>
            <div class="stat-card info">
                <div class="stat-value">{len(unmatched_invoices)}</div>
                <div class="stat-label">Unmatched Invoices</div>
            </div>
        </div>

        <section>
            <h2>Matched Transactions ({len(matched)})</h2>
            {"<p class='empty-state'>No matches found</p>" if not matched else f'''
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th style="text-align:right">Amount</th>
                        <th>Vendor</th>
                        <th>Invoice</th>
                        <th>Confidence</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    {matched_rows}
                </tbody>
            </table>
            '''}
        </section>

        {"" if not unmatched_transactions else f'''
        <section>
            <h2>Unmatched Transactions ({len(unmatched_transactions)})</h2>
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th style="text-align:right">Amount</th>
                        <th>Type</th>
                        <th>Vendor/Note</th>
                        <th>VS</th>
                    </tr>
                </thead>
                <tbody>
                    {unmatched_trans_rows}
                </tbody>
            </table>
        </section>
        '''}

        {"" if not unmatched_invoices else f'''
        <section>
            <h2>Unmatched Invoices ({len(unmatched_invoices)})</h2>
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th style="text-align:right">Amount</th>
                        <th>Type</th>
                        <th>Vendor</th>
                        <th>File</th>
                    </tr>
                </thead>
                <tbody>
                    {unmatched_inv_rows}
                </tbody>
            </table>
        </section>
        '''}

        <footer>
            <p>Reconciliation Tool v1.0</p>
        </footer>
    </div>
</body>
</html>"""

        return html

    def save_report(self, report: str, output_path: Path) -> None:
        """Save HTML report to file."""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)
