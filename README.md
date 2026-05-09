# Invoice Matcher

Match bank transactions with invoice PDFs. Simple 1:1 matching with automatic learning.

## Features

- **Google Login Protection** - All API endpoints are protected by Google sign-in with server-side sessions
- **Google Drive Integration** - Import invoice PDFs from Drive, auto-organize by month
- **Client-Side Encrypted Fio Vault** - The Fio token is encrypted in the browser before being stored on the server
- **Fio Bank API** - Fetch transactions directly from Fio Bank on demand
- **LLM-Powered Parsing** - Extract vendor, amount, date, VS, IBAN from PDFs using OpenRouter
- **E-kasa Receipt Parsing** - Extract data from Slovak receipts via QR code
- **Auto-Matching** - Match by VS, IBAN+amount, or learned vendor aliases
- **Known Transaction Rules** - Auto-skip recurring fees and known payments
- **Export to Accountant** - Copy matched invoices to shared folder with duplicate detection
- **Monthly Summary** - Track income, expenses, fees, and cash by month

## Quick Start

### Docker (Recommended)

```bash
# Create .env file with your credentials
cat > .env << EOF
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-secret
GOOGLE_AUTH_REDIRECT_URI=http://localhost:8000/api/auth/callback
GOOGLE_DRIVE_REDIRECT_URI=http://localhost:8000/api/gdrive/callback
SECRET_KEY=replace-me
ALLOWED_EMAIL_ADDRESSES=you@example.com
OPENROUTER_API_KEY=your-key
OPENROUTER_MODEL=google/gemini-2.0-flash-001
EOF

# Run with pre-built image
docker compose up -d

# Or build locally
docker compose -f docker-compose.build.yml up -d
```

Access at http://localhost:8000

The app now requires Google sign-in before any API access.

### Development Setup

```bash
# Backend
uv sync
cp .env.example .env  # Configure API keys
uv run uvicorn web.main:app --reload --port 8000

# Frontend (in another terminal)
cd frontend && npm install
npm run dev  # Port 5173
```

### Deployment

1. Copy `docker-compose.yml` and `.env` to your server
2. Run:
   ```bash
   docker compose pull
   docker compose up -d
   ```
3. Data is persisted in the `invoice-data` volume

## Security Notes

- All `/api/*` endpoints require authentication except the login bootstrap and health check.
- App sessions are stored server-side and issued through `HttpOnly` cookies with CSRF protection for mutating requests.
- The Fio token is encrypted client-side with Argon2id + AES-GCM before being stored, so the database only contains ciphertext.
- Google Drive credentials are stored per user instead of in global in-memory state.

## Pages

- **Dashboard** - Summary stats, monthly income/expense breakdown, fetch transactions
- **Transactions** - List, filter, match to invoices, skip, create rules
- **Invoices** - Upload, import from GDrive, edit, match to transactions
- **Export** - Download ZIP or copy to accountant folder by month
- **Rules** - Manage known transaction rules for auto-skip
- **Settings** - Fio token, GDrive connection, folder configuration

## Matching Logic

### Auto-Match (Tier 1)
- **VS Match** - Wire transfer with matching variable symbol
- **IBAN + Amount** - Wire transfer with matching IBAN and exact amount

### Learned (Tier 2)
- **Vendor Alias** - Card payment where transaction vendor matches learned alias

### Manual (Tier 3)
- Suggestions ranked by amount similarity, date proximity, vendor similarity

## Invoice Filename Convention

```
YYYY-MM-DD-NNN_type_vendor-slug.pdf
```

- `YYYY-MM-DD` - Invoice date
- `NNN` - Sequence number for that day
- `type` - `card`, `wire`, `cash`, `sepa-debit`, `cod`
- `vendor-slug` - Lowercase, hyphenated vendor name

## License

MIT
