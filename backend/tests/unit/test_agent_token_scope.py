"""Tests for agent-token scoping.

Long-lived agent tokens (issued to the Mac agent, 30-day HS256 JWTs carrying
``{"type": "agent"}``) must NOT be able to reach destructive / account-management
endpoints. They should still reach the upload/sync/read endpoints the agent needs.

These tests exercise the real authentication dependencies with real signed
tokens (no auth override) so that ``request.state.is_agent_token`` is populated
exactly as it would be in production.
"""

from datetime import datetime, timedelta
from typing import Generator

import jwt  # PyJWT — same library clerk.py uses
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models.user import User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_token(user_id: int, *, token_type: str | None) -> str:
    """Sign an HS256 JWT exactly like the backend issues agent/legacy tokens."""
    settings = get_settings()
    claims: dict = {
        "sub": str(user_id),
        "exp": datetime.utcnow() + timedelta(days=1),
    }
    if token_type is not None:
        claims["type"] = token_type
    return jwt.encode(claims, settings.secret_key, algorithm=settings.algorithm)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def scoped_user(db: Session) -> User:
    user = User(
        email="agent-scope@example.com",
        full_name="Agent Scope User",
        clerk_user_id="clerk_agent_scope",
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def scoped_client(db: Session) -> Generator[TestClient, None, None]:
    """A minimal app mounting the real agent-scope guards on test endpoints."""
    from app.auth.clerk import (
        get_clerk_active_user,
        get_clerk_session_user,
        reject_agent_token,
    )

    app = FastAPI()

    @app.get("/agent-allowed")
    async def agent_allowed(user: User = Depends(get_clerk_active_user)):
        return {"user_id": user.id}

    @app.get("/session-only")
    async def session_only(user: User = Depends(get_clerk_session_user)):
        return {"user_id": user.id}

    @app.get("/router-blocked", dependencies=[Depends(reject_agent_token)])
    async def router_blocked():
        return {"ok": True}

    def _get_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)


# ---------------------------------------------------------------------------
# Agent tokens are blocked from session-only / destructive endpoints
# ---------------------------------------------------------------------------


def test_agent_token_blocked_on_session_only_endpoint(scoped_client, scoped_user):
    token = _make_token(scoped_user.id, token_type="agent")
    resp = scoped_client.get("/session-only", headers=_auth(token))
    assert resp.status_code == 403


def test_agent_token_blocked_on_router_level_guard(scoped_client, scoped_user):
    token = _make_token(scoped_user.id, token_type="agent")
    resp = scoped_client.get("/router-blocked", headers=_auth(token))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Agent tokens still work where the agent needs them
# ---------------------------------------------------------------------------


def test_agent_token_allowed_on_agent_endpoint(scoped_client, scoped_user):
    token = _make_token(scoped_user.id, token_type="agent")
    resp = scoped_client.get("/agent-allowed", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["user_id"] == scoped_user.id


# ---------------------------------------------------------------------------
# Non-agent tokens (dashboard / legacy sessions) keep full access
# ---------------------------------------------------------------------------


def test_session_token_allowed_on_session_only_endpoint(scoped_client, scoped_user):
    token = _make_token(scoped_user.id, token_type=None)
    resp = scoped_client.get("/session-only", headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["user_id"] == scoped_user.id


def test_session_token_allowed_on_router_level_guard(scoped_client, scoped_user):
    token = _make_token(scoped_user.id, token_type=None)
    resp = scoped_client.get("/router-blocked", headers=_auth(token))
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Legacy auth chain (decode_access_token) — used by todos/users routers
# ---------------------------------------------------------------------------


@pytest.fixture
def legacy_client(db: Session) -> Generator[TestClient, None, None]:
    """App mounting the real legacy-auth agent-scope guard on a test endpoint."""
    from app.auth.dependencies import get_current_active_user, reject_agent_token_legacy

    app = FastAPI()

    @app.get("/legacy-allowed")
    async def legacy_allowed(user: User = Depends(get_current_active_user)):
        return {"user_id": user.id}

    @app.get("/legacy-blocked", dependencies=[Depends(reject_agent_token_legacy)])
    async def legacy_blocked():
        return {"ok": True}

    def _get_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)


def test_agent_token_blocked_on_legacy_router_guard(legacy_client, scoped_user):
    token = _make_token(scoped_user.id, token_type="agent")
    resp = legacy_client.get("/legacy-blocked", headers=_auth(token))
    assert resp.status_code == 403


def test_legacy_session_token_allowed_on_legacy_router_guard(legacy_client, scoped_user):
    token = _make_token(scoped_user.id, token_type=None)
    resp = legacy_client.get("/legacy-blocked", headers=_auth(token))
    assert resp.status_code == 200
