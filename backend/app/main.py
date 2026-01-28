"""Main FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api import api_router
from app.config import get_settings
from app.middleware.rate_limit import get_rate_limit_key
from app.middleware.security_headers import SecurityHeadersMiddleware

settings = get_settings()

# Rate limiter setup - uses user ID for authenticated requests, IP for unauthenticated
limiter = Limiter(key_func=get_rate_limit_key)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application lifecycle events."""
    # Startup
    print("🚀 Starting rMirror Cloud API...")

    # Start background sync worker
    from app.services.sync_worker import start_sync_worker
    await start_sync_worker(poll_interval=5)

    yield

    # Shutdown
    print("👋 Shutting down rMirror Cloud API...")

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
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}
