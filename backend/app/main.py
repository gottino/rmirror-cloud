"""Main FastAPI application."""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import api_router
from app.config import get_settings
from app.database import get_db
from app.logging_config import configure_logging
from app.middleware.rate_limit import get_rate_limit_key
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

settings = get_settings()

# Configure structured JSON logging before anything else
configure_logging(debug=settings.debug)
logger = logging.getLogger(__name__)

# Rate limiter setup - uses user ID for authenticated requests, IP for unauthenticated
limiter = Limiter(key_func=get_rate_limit_key)


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

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
    checks: dict = {"status": "healthy"}

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
