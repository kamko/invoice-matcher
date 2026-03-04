# invoice-matcher

Automatically reconcile bank statements with invoice PDFs. Matches transactions to invoices using weighted scoring based on amount, vendor name, date proximity, and variable symbol.

## Features

- Parse Fio Bank CSV statements (Slovak format)
- Extract data from invoice PDFs (amount, VS, dates)
- Smart matching with configurable confidence thresholds
- Text and HTML report generation
- Payment type filtering (card vs wire transfers)

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Text report to stdout
python reconcile.py bank_statement.csv invoices_directory/

# Save text report
python reconcile.py bank_statement.csv invoices_directory/ -o report.txt

# Generate HTML report
python reconcile.py bank_statement.csv invoices_directory/ -o report.html

# Open HTML report in browser
python reconcile.py bank_statement.csv invoices_directory/ -o report.html --open
```

## Matching Strategy

| Strategy | Weight | Description |
|----------|--------|-------------|
| Amount | 40% | Exact or near-exact match (5 cent tolerance) |
| Vendor | 25% | Fuzzy name matching |
| Date | 20% | Invoice date near/before transaction |
| VS | 15% | Variable Symbol match (wire transfers) |

### Confidence Thresholds

- **>= 70%**: High confidence match (OK)
- **30-70%**: Needs manual review (REVIEW)
- **< 30%**: No match

## Invoice Naming Convention

```
YYYY-MM-DD-NNN_type_vendor.pdf
```

- `YYYY-MM-DD`: Invoice date
- `NNN`: Sequence number
- `type`: `card` or `wire`
- `vendor`: Vendor identifier

Examples:
- `2026-02-03-001_card_hetzner.pdf`
- `2026-02-14-001_wire_efiia.pdf`

## Project Structure

```
invoice-matcher/
├── reconcile.py          # CLI entry point
├── requirements.txt      # Dependencies
├── models/               # Data models
├── parsers/              # CSV and PDF parsers
├── matching/             # Matching algorithms
└── reports/              # Report generators
```

## License

MIT
