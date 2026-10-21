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


# ---------------------------------------------------------------------------
# The real application: guards are wired onto the routes that need them
# ---------------------------------------------------------------------------
#
# The tests above prove the guard functions work on synthetic routes. These
# check the production routing table, so removing a guard from a real router or
# endpoint fails a test.

API = f"/{get_settings().api_version}"

# Routes an agent token must not reach.
AGENT_BLOCKED_ROUTES = [
    ("POST", f"{API}/integrations/"),
    ("DELETE", f"{API}/integrations/{{target_name}}"),
    ("GET", f"{API}/integrations/notion/databases"),
    ("DELETE", f"{API}/integrations/todoist/disconnect"),
    ("POST", f"{API}/integrations/obsidian/regenerate-key"),
    ("POST", f"{API}/account/export"),
    ("DELETE", f"{API}/account"),
    ("GET", f"{API}/todos/"),
    ("DELETE", f"{API}/todos/{{todo_id}}"),
    ("DELETE", f"{API}/notebooks/{{notebook_id}}"),
    ("GET", f"{API}/notebooks/{{notebook_id}}/export"),
    ("POST", f"{API}/auth/agent-token"),
    ("GET", f"{API}/admin/users"),
    ("GET", f"{API}/waitlist/admin"),
    ("POST", f"{API}/waitlist/admin/{{entry_id}}/approve"),
    ("POST", f"{API}/users/accept-terms"),
    ("POST", f"{API}/sync/trigger"),
    ("POST", f"{API}/sync/process-queue"),
    ("POST", f"{API}/processing/metadata/rebuild-paths"),
]

# Routes the Mac agent calls; guarding any of them would break sync.
AGENT_ALLOWED_ROUTES = [
    ("GET", f"{API}/users/me"),
    ("GET", f"{API}/sync/stats"),
    ("POST", f"{API}/sync/metadata"),
    ("POST", f"{API}/processing/rm-file"),
    ("GET", f"{API}/quota/status"),
    ("POST", f"{API}/agents/register"),
]


def _find_route(method: str, path: str):
    from fastapi.routing import APIRoute

    from app.main import app

    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and method in route.methods:
            return route
    raise AssertionError(f"No route {method} {path} in app.main.app")


def _dependency_calls(dependant) -> set:
    calls = set()
    for sub in dependant.dependencies:
        calls.add(sub.call)
        calls |= _dependency_calls(sub)
    return calls


def _is_agent_guarded(route) -> bool:
    from app.auth.clerk import get_clerk_session_user, reject_agent_token
    from app.auth.dependencies import reject_agent_token_legacy

    guards = {get_clerk_session_user, reject_agent_token, reject_agent_token_legacy}
    return bool(_dependency_calls(route.dependant) & guards)


@pytest.mark.parametrize("method,path", AGENT_BLOCKED_ROUTES)
def test_real_route_rejects_agent_tokens(method, path):
    assert _is_agent_guarded(_find_route(method, path)), f"{method} {path} is not agent-guarded"


@pytest.mark.parametrize("method,path", AGENT_ALLOWED_ROUTES)
def test_real_agent_route_stays_open_to_agent_tokens(method, path):
    assert not _is_agent_guarded(_find_route(method, path)), f"{method} {path} would block the agent"


@pytest.fixture
def real_client(db: Session) -> Generator[TestClient, None, None]:
    """The production app with only the database swapped for the test session."""
    from app.main import app

    def _get_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = _get_db
    try:
        # No ``with`` block: the lifespan (sync worker) must not start.
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", f"{API}/admin/users"),
        ("DELETE", f"{API}/notebooks/999999"),
    ],
)
def test_agent_token_gets_403_from_real_app(real_client, scoped_user, method, path):
    token = _make_token(scoped_user.id, token_type="agent")
    resp = real_client.request(method, path, headers=_auth(token))
    assert resp.status_code == 403
    assert "Agent tokens" in resp.json()["detail"]
