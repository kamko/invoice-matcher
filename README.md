# Invoice Matcher

Internal tool for reconciling Fio Bank transactions with invoice PDFs stored in Google Drive.

Current reality:

- Google sign-in is required to use the app
- the same Google flow is used for Drive access
- invoices are Drive-backed and cached locally in SQLite
- Fio transactions are fetched on demand
- matching is mostly deterministic: VS, IBAN + amount, then learned vendor aliases
- unmatched items are reviewed manually in the UI

## Stack

- FastAPI + SQLAlchemy + SQLite
- React + Vite
- Google OAuth + Google Drive
- Fio Bank API
- optional OpenRouter-based PDF extraction

## Required Config

Copy `.env.example` to `.env` and set at least:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_AUTH_REDIRECT_URI`
- `SECRET_KEY`

Usually also needed:

- `ALLOWED_EMAIL_ADDRESSES` or `ALLOWED_EMAIL_DOMAINS`

Optional:

- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL`

## Run

Prebuilt image:

```bash
docker compose up -d
```

Local build:

```bash
docker compose -f docker-compose.build.yml up -d
```

Development:

```bash
uv sync
uv run uvicorn web.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

- app: [http://localhost:8000](http://localhost:8000)
- frontend dev: [http://localhost:5173](http://localhost:5173)

## Notes

- uploads go to Google Drive month folders named `YYYYMM`
- uploaded files are renamed to `YYYY-MM-DD-NNN_payment-type_vendor-slug.pdf`
- cash invoices are marked as `cash` and do not need a bank transaction match
- export can download a ZIP or copy files into accountant Drive folders
- production Docker image is `ghcr.io/kamko/invoice-matcher:${IMAGE_TAG}`

## License

MIT
