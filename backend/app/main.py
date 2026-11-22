"""Main FastAPI application."""

import logging
import os
import re
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import api_router
from app.config import check_insecure_flags, get_settings, validate_startup
from app.database import get_db
from app.logging_config import configure_logging
from app.middleware.rate_limit import install_rate_limiting
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

settings = get_settings()

# Configure structured JSON logging before anything else
configure_logging(debug=settings.debug)
logger = logging.getLogger(__name__)

# Refuse insecure development flags outside SQLite (warns loudly when allowed)
check_insecure_flags(settings)

# Written by scripts/deploy.sh before it restarts the service.
DEPLOY_COMMIT_FILE = Path(__file__).resolve().parent.parent / ".deploy-commit"


@lru_cache
def deployed_commit() -> str:
    """Git commit this process was deployed from (DEPLOY_COMMIT env, else the file)."""
    value = os.environ.get("DEPLOY_COMMIT", "").strip()
    if not value:
        try:
            value = DEPLOY_COMMIT_FILE.read_text().strip()
        except OSError:
            value = ""
    return value if re.fullmatch(r"[0-9a-f]{7,40}", value) else "unknown"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application lifecycle events."""
    # Startup
    validate_startup(settings, logger)
    logger.info("Starting rMirror Cloud API")

    # Start background sync worker
    from app.services.sync_worker import start_sync_worker
    await start_sync_worker(poll_interval=5)

    yield

    # Shutdown
    logger.info("Shutting down rMirror Cloud API")

    # Stop background sync worker
    from app.services.sync_worker import stop_sync_worker
    await stop_sync_worker()


def api_docs_kwargs(settings) -> dict:
    """FastAPI arguments that turn /docs, /redoc and /openapi.json off unless enabled."""
    if settings.enable_api_docs:
        return {}
    return {"docs_url": None, "redoc_url": None, "openapi_url": None}


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Cloud service for reMarkable tablet integration",
    lifespan=lifespan,
    **api_docs_kwargs(settings),
)

# Shared rate limiter: per-route limits keyed by user, and a default limit
# (per client IP) for every other route. Added first so CORS and security
# headers also wrap 429 responses.
install_rate_limiting(app)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
)

# Add security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Add request context middleware (wraps everything — generates/propagates X-Request-ID, logs timing)
app.add_middleware(RequestContextMiddleware)

# Include API routers
app.include_router(api_router, prefix=f"/{settings.api_version}")


@app.get("/")
async def root():
    """Root endpoint - API health check."""
    return {
        "service": settings.app_name,
        "version": "0.1.0",
        "status": "operational",
    }


@app.get("/health")
async def health(db: Session = Depends(get_db)):
    """Health check endpoint with database and queue status."""
    checks: dict = {"status": "healthy", "commit": deployed_commit()}

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
        checks["status"] = "degraded"

    try:
        from app.models.sync_record import SyncQueue

        pending = db.query(SyncQueue).filter(SyncQueue.status == "pending").count()
        failed = db.query(SyncQueue).filter(SyncQueue.status == "failed").count()
        checks["sync_queue"] = {"pending": pending, "failed": failed}
    except Exception:
        checks["sync_queue"] = "error"

    return checks
