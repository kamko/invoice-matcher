"""Database migrations package."""

from pathlib import Path

from .add_extracted_vendor import migrate as migrate_extracted_vendor
from .add_invoice_currency import migrate as migrate_invoice_currency
from .add_invoice_document_type import migrate as migrate_invoice_document_type


def run_all_migrations(db_path: Path) -> list[str]:
    """Run all migrations and return list of applied migration names."""
    applied = []

    if migrate_extracted_vendor(db_path):
        applied.append("add_extracted_vendor")

    if migrate_invoice_currency(db_path):
        applied.append("add_invoice_currency")

    if migrate_invoice_document_type(db_path):
        applied.append("add_invoice_document_type")

    return applied
