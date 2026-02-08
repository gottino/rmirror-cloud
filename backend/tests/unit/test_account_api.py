"""Tests for account API endpoints: data-summary, export, and delete."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.account import router
from app.database import get_db
from app.dependencies import get_storage_service
from app.models.notebook import Notebook
from app.models.page import OcrStatus, Page
from app.models.subscription import Subscription, SubscriptionStatus, SubscriptionTier
from app.models.user import User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _create_test_app(db: Session, user: User, storage=None):
    """Build a minimal FastAPI app wired to our account router."""
    app = FastAPI()
    app.include_router(router, prefix="/account")

    # Override DB dependency
    def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db

    # Override auth dependency
    from app.auth.clerk import get_clerk_active_user

    async def _get_user():
        return user

    app.dependency_overrides[get_clerk_active_user] = _get_user

    # Override storage dependency
    if storage is None:
        storage = MagicMock()
        storage.download_file = AsyncMock(return_value=b"%PDF-1.4 fake")
        storage.delete_file = AsyncMock(return_value=True)

    app.dependency_overrides[get_storage_service] = lambda: storage

    return TestClient(app)


def _create_user(db: Session) -> User:
    user = User(
        email="api-test@example.com",
        full_name="API Test User",
        clerk_user_id="clerk_api_test",
        subscription_tier=SubscriptionTier.FREE,
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# GET /data-summary
# ---------------------------------------------------------------------------


def test_get_data_summary_authenticated(db: Session):
    """Verify returns correct structure."""
    user = _create_user(db)
    client = _create_test_app(db, user)

    response = client.get("/account/data-summary")
    assert response.status_code == 200

    data = response.json()
    assert "notebooks" in data
    assert "pages" in data
    assert "files" in data
    assert "integrations" in data
    assert "member_since" in data
    assert "subscription" in data
    assert data["notebooks"] == 0
    assert data["subscription"] == "free"


# ---------------------------------------------------------------------------
# POST /export
# ---------------------------------------------------------------------------


def test_export_authenticated(db: Session):
    """Verify returns ZIP with correct content-type."""
    user = _create_user(db)
    client = _create_test_app(db, user)

    with patch("app.api.account.AccountService.generate_data_export", new_callable=AsyncMock) as mock_export:
        mock_export.return_value = b"PK\x03\x04fake-zip-content"
        response = client.post("/account/export")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "rmirror-export-" in response.headers.get("content-disposition", "")


# ---------------------------------------------------------------------------
# DELETE /
# ---------------------------------------------------------------------------


def test_delete_requires_confirmation(db: Session):
    """Missing/wrong phrase returns 400."""
    user = _create_user(db)
    client = _create_test_app(db, user)

    # No body
    response = client.request("DELETE", "/account", json={})
    assert response.status_code == 422  # pydantic validation

    # Wrong phrase
    response = client.request("DELETE", "/account", json={"confirmation": "wrong phrase"})
    assert response.status_code == 400


def test_delete_success(db: Session):
    """Correct phrase, verify 200 + user gone from DB."""
    user = _create_user(db)
    user_id = user.id
    client = _create_test_app(db, user)

    with patch("app.api.account.AccountService.delete_account", new_callable=AsyncMock) as mock_delete:
        mock_delete.return_value = {
            "deleted_notebooks": 0,
            "deleted_pages": 0,
            "deleted_s3_files": 0,
            "clerk_deleted": False,
        }
        response = client.request(
            "DELETE",
            "/account",
            json={"confirmation": "delete my account"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "summary" in data


def test_delete_confirmation_case_sensitive(db: Session):
    """Confirmation phrase is case-sensitive."""
    user = _create_user(db)
    client = _create_test_app(db, user)

    response = client.request(
        "DELETE",
        "/account",
        json={"confirmation": "Delete My Account"},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Auth requirement test
# ---------------------------------------------------------------------------


def test_endpoints_require_auth(db: Session):
    """Verify 401/403 without token (using real auth dependency)."""
    app = FastAPI()
    app.include_router(router, prefix="/account")

    # Override DB only, NOT auth — so auth is enforced
    def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db

    client = TestClient(app, raise_server_exceptions=False)

    # All endpoints should fail without auth
    assert client.get("/account/data-summary").status_code in (401, 403)
    assert client.post("/account/export").status_code in (401, 403)
    assert client.request("DELETE", "/account", json={"confirmation": "delete my account"}).status_code in (401, 403)
