"""Local UI mocks. Run: uv run python tests/mock_preview.py (after frontend build).

Uses an in-memory test database and mocked Drive/Mailjet; no real handoffs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response

from test_accountant_handoff import HandoffTests
from web.routers.dashboard import get_accountant_email_preview, get_dashboard, CopyToAccountantRequest
from web.routers.invoices import list_invoices, update_invoice
from web.schemas.invoices import InvoiceUpdate

fixture = HandoffTests()
fixture.setUp()
fixture.invoice('2026-08-03-001_card_office', vendor='Office supplies', amount='84.90')
fixture.invoice('2026-08-12-002_wire_hosting', vendor='Hosting', amount='29.00', comment='Annual subscription, paid in August.')
fixture.invoice('2026-08-01-003_card_fuel', status='exported', vendor='Fuel', comment='Vehicle KE885HH; handed over earlier.')
app = FastAPI()
dist = Path(__file__).resolve().parents[1] / 'frontend' / 'dist'


@app.get('/api/{path:path}')
async def mock_get(path: str, request: Request):
    if path == 'auth/me':
        return {'authenticated': True, 'csrf_token': 'mock', 'user': {'id': 1, 'email': 'demo@example.com', 'full_name': 'MOCK DATA — no real handoffs'}}
    if path == 'dashboard':
        return get_dashboard(fixture.user, fixture.db)
    if path == 'invoices':
        return list_invoices(request.query_params.get('month'), request.query_params.get('status'), None, fixture.user, fixture.db)
    if path.endswith('email-preview'):
        return get_accountant_email_preview('2026-08', fixture.user, fixture.db, request.query_params.get('complete_month') == 'true')
    if path == 'settings':
        return {'company_name': 'Demo Company', 'accountant_folder_id': 'mock', 'accountant_email': 'accountant@example.com', 'mailjet_sender_email': 'demo@example.com'}
    if path == 'gdrive/status':
        return {'available': True, 'authenticated': True}
    if 'sender-status' in path:
        return {'active': True}
    if path == 'settings/config':
        return {'mailjet_enabled': True}
    if path == 'vehicles':
        return []
    if path == 'sse/events':
        return Response(status_code=204)
    return {'configured': False, 'mailjet_enabled': True}


@app.post('/api/export/{month}/copy-to-gdrive')
async def mock_handoff(month: str, payload: CopyToAccountantRequest):
    return fixture.handoff(**payload.model_dump())


@app.patch('/api/invoices/{invoice_id}')
async def mock_edit(invoice_id: int, payload: InvoiceUpdate):
    return update_invoice(invoice_id, payload, fixture.user, fixture.db)


@app.get('/{path:path}')
async def page(path: str):
    target = (dist / path).resolve()
    if target.is_relative_to(dist) and target.is_file():
        return FileResponse(target)
    return FileResponse(dist / 'index.html')


if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=8765)
