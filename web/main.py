"""FastAPI application for invoice matcher v2."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from web.config import settings, BASE_DIR
from web.database import init_db
from web.routers.invoices import router as invoices_router
from web.routers.transactions import router as transactions_router
from web.routers.dashboard import router as dashboard_router
from web.routers.known_transactions import router as known_transactions_router
from web.routers.gdrive import router as gdrive_router
from web.routers.settings import router as settings_router
from web.routers.sse import router as sse_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    init_db()
    yield
    # Shutdown


app = FastAPI(
    title="Invoice Matcher API",
    description="API for reconciling bank transactions with invoices",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(invoices_router)
app.include_router(transactions_router)
app.include_router(dashboard_router)
app.include_router(known_transactions_router)
app.include_router(gdrive_router)
app.include_router(settings_router)
app.include_router(sse_router)


@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": "2.0.0"}


@app.get("/api/config")
def get_config():
    """Get public application config."""
    return {
        "llm_model": settings.openrouter_model,
        "llm_enabled": bool(settings.openrouter_api_key),
    }


# Serve frontend static files in production
FRONTEND_DIR = BASE_DIR / "frontend" / "dist"

if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve frontend SPA."""
        # Check if it's an API route
        if full_path.startswith("api/"):
            return {"error": "Not found"}

        # Serve index.html for all other routes (SPA routing)
        index_path = FRONTEND_DIR / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {"error": "Frontend not built"}
