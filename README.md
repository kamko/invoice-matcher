# Invoice Matcher

Match bank transactions with invoice PDFs. Simple 1:1 matching with automatic learning.

## Features

- **Flat Data Model** - Invoices and transactions as independent tables with 1:1 matching
- **Google Drive Integration** - Import invoice PDFs from Drive, rename files in-place
- **Fio Bank API** - Fetch transactions directly from Fio Bank
- **LLM-Powered Parsing** - Extract vendor, amount, date, VS, IBAN from PDFs using OpenRouter
- **E-kasa Receipt Parsing** - Extract data from Slovak receipts via QR code
- **Auto-Matching** - Match by VS, IBAN+amount, or learned vendor aliases
- **Known Transaction Rules** - Auto-skip recurring fees and known payments
- **Real-time SSE Updates** - Live progress during sync operations

## Quick Start

### Docker (Recommended)

```bash
# Create .env file with your credentials
cat > .env << EOF
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-secret
OPENROUTER_API_KEY=your-key
OPENROUTER_MODEL=google/gemini-2.0-flash-001
EOF

# Run with pre-built image
docker compose up -d

# Or build locally
docker compose -f docker-compose.build.yml up -d
```

Access at http://localhost:8000

### Development Setup

```bash
# Backend
cd fa
uv sync
cp .env.example .env  # Configure API keys

# Start backend (port 8000)
uv run uvicorn web.main:app --reload --port 8000

# Frontend (in another terminal)
cd frontend && npm install
npm run dev  # Port 5173
```

### Environment Variables

```env
# Google Drive OAuth (optional)
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-secret

# LLM for invoice parsing (optional but recommended)
OPENROUTER_API_KEY=your-key
OPENROUTER_MODEL=google/gemini-2.0-flash-001
```

### Deployment

1. Copy `docker-compose.yml` and `.env` to your server
2. Run:
   ```bash
   docker compose pull
   docker compose up -d
   ```
3. Data is persisted in the `invoice-data` volume

## Pages

### Dashboard (`/`)
- Summary stats: unmatched transactions/invoices, matched this month
- Quick actions: Fetch transactions, Import from GDrive

### Transactions (`/transactions`)
- List with filters: month, status (unmatched/matched/known/skipped), type (expense/income/fee)
- Match to invoice, skip with reason, or create known rule
- View suggested invoice matches

### Invoices (`/invoices`)
- List with filters: month, status (unmatched/matched/exported)
- Upload PDF with drag & drop, auto-analyze to prefill fields
- Edit with re-analyze, auto-generated filename preview
- Match to transaction with suggestions

### Settings (`/settings`)
- Fio Bank API token (stored in browser localStorage)
- Google Drive connection (OAuth flow)
- Invoice folder picker
- LLM configuration display

## Matching Logic

### Tier 1: Deterministic (auto-match)
- **VS Match**: Wire transfer with matching variable symbol
- **IBAN + Amount**: Wire transfer with matching IBAN and exact amount

### Tier 2: Learned (auto-match)
- **Vendor Alias**: Card payment where transaction vendor matches a learned alias

### Tier 3: Suggestions (manual)
- Ranked by: amount similarity, date proximity, vendor similarity

## Invoice Filename Convention

```
YYYY-MM-DD-NNN_type_vendor-slug.pdf
```

- `YYYY-MM-DD`: Invoice date (date of taxable supply)
- `NNN`: Sequence number for that day
- `type`: `card`, `wire`, `cash`, `sepa-debit`
- `vendor-slug`: Lowercase, hyphenated vendor name

Examples:
- `2026-03-07-001_card_obi.pdf`
- `2026-02-14-001_wire_e-fiia-sro.pdf`

## Data Model

### Invoices
- Imported from GDrive or uploaded manually
- Fields: filename, vendor, amount, invoice_date, payment_type, vs, iban
- Status: unmatched, matched, cash, exported
- 1:1 link to transaction via `transaction_id`

### Transactions
- Fetched from Fio Bank API
- Fields: date, amount, counter_account, counter_name, vs, note, type
- Status: unmatched, matched, known, skipped
- Linked to known_transaction rule if auto-matched

### Known Transactions
- Rules for auto-skipping recurring payments
- Types: exact, pattern, vendor, note, account
- Example: Skip all "Dan - preddavok" tax payments

## License

MIT
