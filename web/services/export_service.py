"""Shared eligibility and accountant handoff messages."""

from sqlalchemy import and_, exists

from web.database.models import Invoice, Transaction
from web.services.email_service import DEFAULT_ACCOUNTANT_EMAIL_TEMPLATE, build_accountant_email_body


def exportable_conditions(user_id: int):
    return (
        Invoice.user_id == user_id,
        Invoice.status == 'matched',
        Invoice.include_in_export.is_(True),
        Invoice.parent_invoice_id.is_(None),
        Invoice.gdrive_file_id.isnot(None),
        Invoice.invoice_date.isnot(None),
        exists().where(and_(
            Transaction.id == Invoice.transaction_id,
            Transaction.user_id == user_id,
            Transaction.status == 'matched',
        )),
    )


def handoff_body(year, month, invoices, template=DEFAULT_ACCOUNTANT_EMAIL_TEMPLATE, company_name=""):
    """Keep the saved message, include all notes, and confirm completion."""
    if '{comments}' not in template:
        template += '\n\n{comments}'
    template += '\n\nVšetky doklady za obdobie {period} sú odovzdané.'
    return build_accountant_email_body(year, month, invoices, template, company_name)
