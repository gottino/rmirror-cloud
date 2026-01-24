"""Test configuration for FastAPI application.

Provides a properly configured FastAPI test app with:
- Disabled lifespan (no background workers)
- Mocked authentication
- Test database
- All routes registered
"""

from contextlib import asynccontextmanager
from typing import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import api_router
from app.database import get_db


@asynccontextmanager
async def noop_lifespan(app: FastAPI):
    """No-op lifespan for testing - no background workers."""
    print("🧪 Test mode - skipping background workers")
    yield
    print("🧪 Test cleanup")


def create_test_app() -> FastAPI:
    """Create FastAPI app configured for testing.

    Returns:
        Configured FastAPI application for testing
    """
    app = FastAPI(
        title="rMirror Cloud API (Test)",
        version="0.1.0-test",
        description="Test instance",
        lifespan=noop_lifespan,  # Use no-op lifespan (no background workers)
    )

    # Include API routers (same as production)
    app.include_router(api_router, prefix="/v1")

    @app.get("/")
    async def root():
        return {"service": "rMirror Cloud API (Test)", "status": "test"}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app


@pytest.fixture(scope="function")
def test_app(db: Session) -> Generator[FastAPI, None, None]:
    """Create test app with database override.

    Args:
        db: Test database session

    Yields:
        Configured test app
    """
    app = create_test_app()

    # Override database dependency
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    yield app

    # Clear overrides
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def test_client(test_app: FastAPI) -> TestClient:
    """Create test client.

    Args:
        test_app: Configured test app

    Returns:
        FastAPI test client
    """
    return TestClient(test_app)
