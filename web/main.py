"""FastAPI application for invoice matcher v2."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from web.auth import get_session_from_request, touch_session
from web.config import settings, BASE_DIR
from web.database import SessionLocal, init_db
from web.database.models import User
from web.routers.auth import router as auth_router
from web.routers.invoices import router as invoices_router
from web.routers.transactions import router as transactions_router
from web.routers.dashboard import router as dashboard_router
from web.routers.known_transactions import router as known_transactions_router
from web.routers.gdrive import router as gdrive_router
from web.routers.settings import router as settings_router
from web.routers.secrets import router as secrets_router
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

app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PUBLIC_API_PATHS = {
    "/api/health",
    "/api/auth/login",
    "/api/auth/callback",
}


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    """Attach auth/session state and enforce CSRF on mutating API requests."""
    path = request.url.path

    if request.method != "OPTIONS" and path.startswith("/api/") and path not in PUBLIC_API_PATHS:
        db = SessionLocal()
        try:
            session = get_session_from_request(db, request)
            if not session:
                return JSONResponse(status_code=401, content={"detail": "Authentication required"})

            user = db.query(User).filter(User.id == session.user_id, User.is_active.is_(True)).first()
            if not user:
                return JSONResponse(status_code=401, content={"detail": "Authentication required"})

            if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                csrf_token = request.headers.get("X-CSRF-Token")
                if csrf_token != session.csrf_token:
                    return JSONResponse(status_code=403, content={"detail": "Invalid CSRF token"})

            request.state.session = session
            request.state.user = user
            touch_session(db, session)
        finally:
            db.close()

    response = await call_next(request)
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; "
        "connect-src 'self' https://accounts.google.com https://oauth2.googleapis.com https://www.googleapis.com; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self' https://accounts.google.com;",
    )
    return response

# Include routers
app.include_router(auth_router)
app.include_router(invoices_router)
app.include_router(transactions_router)
app.include_router(dashboard_router)
app.include_router(known_transactions_router)
app.include_router(gdrive_router)
app.include_router(settings_router)
app.include_router(secrets_router)
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
