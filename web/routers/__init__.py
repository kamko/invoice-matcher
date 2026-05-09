"""API routers package."""

from .invoices import router as invoices_router
from .transactions import router as transactions_router
from .dashboard import router as dashboard_router
from .known_transactions import router as known_transactions_router
from .gdrive import router as gdrive_router
from .auth import router as auth_router
from .secrets import router as secrets_router

__all__ = [
    "auth_router",
    "invoices_router",
    "transactions_router",
    "dashboard_router",
    "known_transactions_router",
    "gdrive_router",
    "secrets_router",
]
