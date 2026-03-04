# invoice-matcher

Automatically reconcile bank statements with invoice PDFs. Matches transactions to invoices using weighted scoring based on amount, vendor name, date proximity, and variable symbol.

## Features

- Parse Fio Bank CSV statements (Slovak format)
- **Fetch transactions directly from Fio Bank API**
- Extract data from invoice PDFs (amount, VS, dates)
- Smart matching with configurable confidence thresholds
- Text and HTML report generation
- Payment type filtering (card vs wire transfers)

## Installation

```bash
uv sync
```

Or with pip:

```bash
pip install -r requirements.txt
```

## Usage

### From CSV File

```bash
# Text report to stdout
uv run python reconcile.py bank_statement.csv invoices/

# Generate HTML report
uv run python reconcile.py bank_statement.csv invoices/ -o report.html

# Open HTML report in browser
uv run python reconcile.py bank_statement.csv invoices/ -o report.html --open
```

### From Fio Bank API

Fetch transactions directly from Fio Bank using their API. You'll need an API token from your Fio internet banking settings.

```bash
# Set token as environment variable
export FIO_API_TOKEN=your_token_here
uv run python reconcile.py --api --from 2026-02-01 --to 2026-02-28 invoices/ -o report.html

# Or pass token as argument
uv run python reconcile.py --api --token YOUR_TOKEN --from 2026-02-01 --to 2026-02-28 invoices/
```

**Note**: Fio API has a rate limit of one request per 30 seconds per token.

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
