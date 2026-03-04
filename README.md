# Invoice Matcher

Automatically reconcile bank statements with invoice PDFs. Matches transactions to invoices using weighted scoring based on amount, vendor name, date proximity, and variable symbol.

## Features

- **Web Application** with month-based reconciliation
- **Google Drive Integration** - fetch invoice PDFs directly from Drive
- **Fio Bank API** - fetch transactions directly from Fio Bank
- Extract data from invoice PDFs (amount, VS, dates)
- Smart matching with configurable confidence thresholds
- Mark transactions as "known" (recurring payments, loans, etc.)
- Upload PDFs for unmatched transactions
- Real-time progress updates during sync

## Quick Start

### Docker (Recommended)

```bash
# Create .env file with Google OAuth credentials (optional)
echo "GOOGLE_CLIENT_ID=your-client-id" > .env
echo "GOOGLE_CLIENT_SECRET=your-secret" >> .env

# Start the application
docker compose up -d
```

Open http://localhost:8000 in your browser.

Data is persisted in a Docker volume (`invoice-data`).

### Development Setup

```bash
# Backend
uv sync

# Frontend
cd frontend && npm install

# Start backend (port 8000)
uv run uvicorn web.main:app --reload

# Start frontend (port 5173) - in another terminal
cd frontend && npm run dev
```

For Google Drive integration, set up OAuth credentials in Google Cloud Console.

## Web Application

### Home Page

- **Settings** - Configure Fio Bank API token and connect Google Drive
- **Sync Month** - Select a month and invoice folder, then sync
- **Monthly Reports** - View existing reconciliation results

### Sync Flow

1. Select month (e.g., "February 2026")
2. Select Google Drive folder containing invoices for that month
3. Click "Sync" - progress toast shows real-time updates:
   - Fetching transactions from Fio Bank
   - Downloading invoices from Google Drive
   - Checking known transaction rules
   - Matching transactions with invoices
   - Saving results
4. View report with matched/unmatched transactions

### Report Features

- **Unmatched Tab** - Transactions without matching invoices
  - Upload invoice PDF to match
  - Mark as "known" (recurring payments, subscriptions, etc.)
- **Matched Tab** - Transactions successfully matched with invoices
- **Known Tab** - Transactions matched by known rules
- **Fees Tab** - Bank fees
- **Income Tab** - Incoming transactions

### Known Transaction Rules

Create rules to automatically recognize recurring transactions:
- **Note Pattern** - Match by regex pattern in transaction note
- **Vendor Pattern** - Match by vendor name pattern
- **Exact** - Match exact amount and account

## CLI Usage

The CLI is still available for quick reconciliation:

```bash
# From Fio Bank API
uv run python reconcile.py --api --from 2026-02-01 --to 2026-02-28 invoices/ -o report.html

# From CSV file
uv run python reconcile.py bank_statement.csv invoices/ -o report.html
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

## License

MIT
