# Invoice Matcher

Automatically reconcile bank statements with invoice PDFs. Matches transactions to invoices using weighted scoring based on amount, vendor name, date proximity, and variable symbol.

## Features

- **Web Application** with wizard-style interface
- **Google Drive Integration** - fetch invoice PDFs directly from Drive
- **Fio Bank API** - fetch transactions directly from Fio Bank
- Extract data from invoice PDFs (amount, VS, dates)
- Smart matching with configurable confidence thresholds
- Mark transactions as "known" (recurring payments, loans, etc.)
- Upload PDFs for unmatched transactions
- Real-time progress updates during processing

## Quick Start

### 1. Install Dependencies

```bash
# Backend
uv sync

# Frontend
cd frontend && npm install
```

### 2. Configure Environment

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

For Google Drive integration, set up OAuth credentials in Google Cloud Console and add:
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`

### 3. Run the Application

```bash
# Start backend (port 8000)
uv run uvicorn web.main:app --reload

# Start frontend (port 5173) - in another terminal
cd frontend && npm run dev
```

Open http://localhost:5173 in your browser.

## Web Application

### Wizard Flow

1. **Date Range** - Select the period for reconciliation
2. **Google Drive** - Connect and select folder with invoice PDFs
3. **Bank Token** - Enter your Fio Bank API token
4. **Processing** - Real-time progress with step-by-step updates
5. **Report** - View results with matched/unmatched transactions

### Report Features

- **Matched Tab** - Transactions successfully matched with invoices
- **Unmatched Tab** - Transactions without matching invoices
  - Upload invoice PDF to match
  - Mark as "known" (skip recurring payments)
- **Known Tab** - Transactions marked as known

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

## Project Structure

```
invoice-matcher/
├── reconcile.py          # CLI entry point
├── models/               # Data models
├── parsers/              # CSV and PDF parsers
├── matching/             # Matching algorithms
├── reports/              # Report generators
├── web/                  # FastAPI backend
│   ├── main.py           # App entry point
│   ├── config.py         # Settings
│   ├── database/         # SQLAlchemy models
│   ├── services/         # Business logic
│   ├── routers/          # API endpoints
│   └── schemas/          # Pydantic models
└── frontend/             # React SPA
    ├── src/
    │   ├── pages/        # Page components
    │   ├── components/   # UI components
    │   └── api/          # API client
    └── package.json
```

## License

MIT
