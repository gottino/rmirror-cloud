"""Main FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import api_router
from app.config import check_insecure_flags, get_settings
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application lifecycle events."""
    # Startup
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


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Cloud service for reMarkable tablet integration",
    lifespan=lifespan,
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


# /health reports sync_queue counts up to this value; larger counts show as the cap.
HEALTH_QUEUE_COUNT_CAP = 1000


def _capped_queue_count(db: Session, status: str) -> int:
    """Number of sync_queue rows with this status, counted up to the cap."""
    return db.execute(
        text(
            "SELECT COUNT(*) FROM "
            "(SELECT 1 FROM sync_queue WHERE status = :status LIMIT :cap) AS capped"
        ),
        {"status": status, "cap": HEALTH_QUEUE_COUNT_CAP},
    ).scalar_one()


@app.get("/health")
async def health(db: Session = Depends(get_db)):
    """Health check endpoint with database and queue status."""
    checks: dict = {"status": "healthy"}

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
        checks["status"] = "degraded"

    try:
        # Bounded counts: each reads at most HEALTH_QUEUE_COUNT_CAP index
        # entries, so a probe stays cheap however large the queue grows.
        checks["sync_queue"] = {
            status: _capped_queue_count(db, status) for status in ("pending", "failed")
        }
    except Exception:
        checks["sync_queue"] = "error"

    return checks
