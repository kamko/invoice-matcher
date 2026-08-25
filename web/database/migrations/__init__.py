"""Database migrations package."""

from pathlib import Path

from .add_extracted_vendor import migrate as migrate_extracted_vendor
from .add_invoice_currency import migrate as migrate_invoice_currency
from .add_invoice_document_type import migrate as migrate_invoice_document_type
from .add_invoice_comment import migrate as migrate_invoice_comment
from .add_invoice_upload_metadata import migrate as migrate_invoice_upload_metadata
from .add_vehicles import migrate as migrate_vehicles
from .add_user_scoping import migrate as migrate_user_scoping


def run_all_migrations(db_path: Path) -> list[str]:
    """Run all migrations and return list of applied migration names."""
    applied = []

    if migrate_extracted_vendor(db_path):
        applied.append("add_extracted_vendor")

    if migrate_invoice_currency(db_path):
        applied.append("add_invoice_currency")

    if migrate_invoice_document_type(db_path):
        applied.append("add_invoice_document_type")

    if migrate_invoice_comment(db_path):
        applied.append("add_invoice_comment")

    if migrate_user_scoping(db_path):
        applied.append("add_user_scoping")

    if migrate_invoice_upload_metadata(db_path):
        applied.append("add_invoice_upload_metadata")

    if migrate_vehicles(db_path):
        applied.append("add_vehicles")

    return applied
