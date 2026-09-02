# Invoice Matcher

Private web app for collecting invoices, reconciling them with bank transactions, and handing a complete monthly package to an accountant.

## What It Does

- requires Google sign-in and keeps business data scoped to the signed-in user
- connects to Google Drive through the same Google authorization flow
- uploads PDFs or imports existing Drive month folders
- supports selecting multiple PDFs at once and choosing which files belong in the accountant export
- detects invoice attachments, links them to one primary document, and names them with `_att_01`, `_att_02`, and so on
- blocks byte-identical duplicate PDFs before they are uploaded to Drive
- manages a per-user vehicle list in Settings and includes the selected vehicle registration in expense filenames
- extracts invoice metadata with deterministic parsing and optional LLM assistance
- classifies documents as invoices, receipts, or other documents
- fetches bank transactions on demand and supports deterministic, learned, suggested, and manual matching
- stores optional accountant comments on individual documents
- exports a month as a ZIP or copies documents into an accountant Drive folder
- optionally adds the monthly bank statement to the accountant export
- previews and sends a summary email through Mailjet, including document comments and a BCC to the signed-in user
- supports editable organization name, email subject template, message template, sender identity, and accountant recipient in Settings

## Stack

- FastAPI, SQLAlchemy, and SQLite
- React, TypeScript, and Vite
- Google OAuth and Google Drive API
- Fio API for transactions and monthly statements
- optional OpenRouter-based PDF extraction
- optional Mailjet transactional email

## Configuration

Copy `.env.example` to `.env`.

Required for sign-in and Drive access:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_AUTH_REDIRECT_URI`
- `SECRET_KEY`
- `TRUSTED_HOSTS`

Access control is optional but strongly recommended for any deployed instance:

- `ALLOWED_EMAIL_ADDRESSES`
- `ALLOWED_EMAIL_DOMAINS`

If both allowlists are empty, any Google account that can complete sign-in is accepted.

Optional integrations:

- `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` enable LLM-assisted extraction
- `MAILJET_API_KEY` and `MAILJET_SECRET_KEY` enable accountant summary emails
- `ENCRYPTION_KEY` provides a dedicated server-side key for stored Google credentials; `SECRET_KEY` is used as the fallback

Mailjet sender details, organization name, subject and message templates, recipient, and Drive folder IDs are configured per user in the app Settings. They are not environment variables.

For HTTPS deployments, set `SESSION_COOKIE_SECURE=true` and use the public HTTPS callback URL in `GOOGLE_AUTH_REDIRECT_URI`.

## Run

Prebuilt image:

```bash
docker compose up -d
```

Local image build:

```bash
docker compose -f docker-compose.build.yml up -d --build
```

Development backend:

```bash
uv sync
uv run uvicorn web.main:app --reload --port 8000
```

Development frontend:

```bash
cd frontend
npm install
npm run dev
```

- production-style app: [http://localhost:8000](http://localhost:8000)
- frontend development server: [http://localhost:5173](http://localhost:5173)
- health check: [http://localhost:8000/api/health](http://localhost:8000/api/health)

## First-Run Setup

1. Sign in with Google and grant Drive access.
2. In Settings, choose the invoice parent folder and accountant shared root folder.
3. Add the vehicles used for fuel and other car expenses.
4. Save the Fio token in the encrypted vault if transaction fetching or monthly statement export is needed.
5. If email handoff is enabled, configure the organization name, subject template, sender, recipient, and message template.
6. Import existing Drive folders or upload invoice PDFs.

The default email subject template is:

```text
{company_name} - Doklady za obdobie {period}
```

Both subject tokens are required. The message template supports `{company_name}`, `{period}`, and `{comments}`. When no document has a comment, the standalone `{comments}` line and excess spacing are removed.

## Data and Security

- SQLite data and cached PDFs live in the persistent `/app/data` Docker volume.
- Google credentials are encrypted server-side before storage.
- The Fio token is encrypted in the browser with AES-GCM using a key derived with Argon2id; only the encrypted payload is stored by the server.
- The Fio vault password can be remembered for the current tab or, when explicitly selected, on the current device.
- Mutating API requests require a valid authenticated session and CSRF token.
- OpenRouter and Mailjet API keys remain server-side environment variables.

Back up the persistent data volume before replacing or migrating a deployment.

## Workflow Notes

- uploaded files go into Drive month folders named `YYYYMM`
- uploaded files are renamed to `YYYY-MM-DD-NNN_payment-type_vendor-slug.pdf`
- vehicle expenses use the active vehicle dropdown; with one active vehicle it is selected automatically
- vehicle-expense filenames add the selected registration before `.pdf`
- changing a vehicle in Settings affects future uploads while existing documents keep their stored registration
- files excluded from accountant export remain available as internal references and are not bank-matched
- supporting attachments do not store their own amount or payment type and do not consume invoice sequence numbers
- cash invoices use the `cash` status and do not require a bank transaction match
- accountant exports route files by document type into `POKLADNICNE_DOKLADY`, `DOSLE_FAKTURY`, and `OSTATNE`
- the optional monthly statement is stored in `OSTATNE`
- email preview shows From, To, BCC, subject, and the editable per-send message body
- editing the preview body does not overwrite the saved message template

## Verification

Backend tests:

```bash
uv run python -m unittest discover -s tests -v
```

Frontend production build:

```bash
cd frontend
npm run build
```

## License

MIT
