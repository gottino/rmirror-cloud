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
# HS256 tokens that are not agent tokens must not authenticate at all.
# Before this was enforced, a token from the old /auth/login endpoint (no
# ``type`` claim) was treated as a full dashboard session.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("token_type", [None, "access", "session", "invite"])
@pytest.mark.parametrize("path", ["/agent-allowed", "/session-only", "/router-blocked"])
def test_non_agent_hs256_token_is_rejected(scoped_client, scoped_user, token_type, path):
    token = _make_token(scoped_user.id, token_type=token_type)
    resp = scoped_client.get(path, headers=_auth(token))
    assert resp.status_code == 401


def test_hs256_token_signed_with_wrong_key_is_rejected(scoped_client, scoped_user):
    token = jwt.encode(
        {"sub": str(scoped_user.id), "type": "agent", "exp": datetime.utcnow() + timedelta(days=1)},
        "not-the-server-secret",
        algorithm="HS256",
    )
    resp = scoped_client.get("/agent-allowed", headers=_auth(token))
    assert resp.status_code == 401


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
    ("POST", f"{API}/auth/agent-token/revoke"),
    ("GET", f"{API}/admin/users"),
    ("GET", f"{API}/waitlist/admin"),
    ("POST", f"{API}/waitlist/admin/{{entry_id}}/approve"),
    ("POST", f"{API}/users/accept-terms"),
    ("POST", f"{API}/sync/trigger"),
    ("POST", f"{API}/processing/metadata/rebuild-paths"),
    # Read the user's notebook content; the agent never calls them.
    ("GET", f"{API}/notebooks/"),
    ("GET", f"{API}/notebooks/tree"),
    ("GET", f"{API}/notebooks/uuid/{{notebook_uuid}}"),
    ("GET", f"{API}/notebooks/{{notebook_id}}"),
    ("GET", f"{API}/notebooks/{{notebook_id}}/pages"),
    ("GET", f"{API}/pages/{{page_id}}/pdf"),
    ("GET", f"{API}/search"),
]

# Routes the Mac agent calls; guarding any of them would break sync.
AGENT_ALLOWED_ROUTES = [
    ("GET", f"{API}/users/me"),
    ("GET", f"{API}/sync/stats"),
    ("POST", f"{API}/sync/metadata"),
    ("POST", f"{API}/processing/rm-file"),
    ("GET", f"{API}/quota/status"),
    ("POST", f"{API}/agents/register"),
    ("POST", f"{API}/processing/metadata/update"),
    ("POST", f"{API}/notebooks/{{notebook_uuid}}/content"),
    ("GET", f"{API}/sync/deleted-notebooks"),
    ("POST", f"{API}/sync/deleted-notebooks/{{notebook_uuid}}/acknowledge"),
]

# Routes an agent token can reach although the agent does not call them.
# Reviewed and left open for now (low sensitivity, or writes whose guard needs
# a separate decision); each one is a candidate for a guard.
AGENT_REACHABLE_UNUSED_ROUTES = [
    ("GET", f"{API}/users/legal-status"),
    ("GET", f"{API}/onboarding/progress"),
    ("POST", f"{API}/onboarding/progress"),
    ("POST", f"{API}/onboarding/agent-downloaded"),
    ("POST", f"{API}/onboarding/dismiss"),
    ("POST", f"{API}/agents/heartbeat"),
    ("GET", f"{API}/agents/status"),
    ("POST", f"{API}/notebooks/upload"),
    ("GET", f"{API}/quota/check"),
    ("GET", f"{API}/sync/status/{{target_name}}"),
]

# Routes that do not take Clerk or agent bearer tokens at all.
NON_CLERK_ROUTES = [
    # Public
    ("GET", "/"),
    ("GET", "/health"),
    ("GET", f"{API}/agents/latest-version"),
    ("GET", f"{API}/agents/clerk-config"),
    ("POST", f"{API}/waitlist"),
    ("GET", f"{API}/waitlist/validate-invite"),
    # Webhook signature
    ("POST", f"{API}/webhooks/clerk"),
    # Obsidian API key
    ("GET", f"{API}/integrations/obsidian/sync"),
    ("POST", f"{API}/integrations/obsidian/sync/confirm"),
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

    guards = {get_clerk_session_user, reject_agent_token}
    return bool(_dependency_calls(route.dependant) & guards)


@pytest.mark.parametrize("method,path", AGENT_BLOCKED_ROUTES)
def test_real_route_rejects_agent_tokens(method, path):
    assert _is_agent_guarded(_find_route(method, path)), f"{method} {path} is not agent-guarded"


@pytest.mark.parametrize("method,path", AGENT_ALLOWED_ROUTES)
def test_real_agent_route_stays_open_to_agent_tokens(method, path):
    assert not _is_agent_guarded(_find_route(method, path)), f"{method} {path} would block the agent"


@pytest.mark.parametrize("method,path", AGENT_REACHABLE_UNUSED_ROUTES)
def test_reviewed_unused_route_is_listed_correctly(method, path):
    route = _find_route(method, path)
    assert not _is_agent_guarded(route), (
        f"{method} {path} is guarded now; move it to AGENT_BLOCKED_ROUTES"
    )


@pytest.mark.parametrize("method,path", NON_CLERK_ROUTES)
def test_non_clerk_route_does_not_use_clerk_auth(method, path):
    from app.auth.clerk import get_clerk_user

    route = _find_route(method, path)
    assert get_clerk_user not in _dependency_calls(route.dependant), (
        f"{method} {path} uses Clerk/agent auth; classify it as agent-allowed or guard it"
    )


def test_every_route_is_classified_for_agent_tokens():
    """Each route must be agent-guarded, agent-allowed, reviewed, or non-Clerk.

    A new router or endpoint fails this test until someone decides whether
    the Mac agent's long-lived token may call it.
    """
    from fastapi.routing import APIRoute

    from app.main import app

    open_to_agent = set(AGENT_ALLOWED_ROUTES) | set(AGENT_REACHABLE_UNUSED_ROUTES)
    non_clerk = set(NON_CLERK_ROUTES)
    unclassified = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            key = (method, route.path)
            if _is_agent_guarded(route) or key in open_to_agent or key in non_clerk:
                continue
            unclassified.append(f"{method} {route.path}")
    assert not unclassified, (
        "Routes not classified for agent tokens (guard them with "
        "get_clerk_session_user/reject_agent_token, or add them to "
        "AGENT_ALLOWED_ROUTES / AGENT_REACHABLE_UNUSED_ROUTES / NON_CLERK_ROUTES): "
        + ", ".join(unclassified)
    )


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
        ("GET", f"{API}/todos/"),
    ],
)
def test_agent_token_gets_403_from_real_app(real_client, scoped_user, method, path):
    token = _make_token(scoped_user.id, token_type="agent")
    resp = real_client.request(method, path, headers=_auth(token))
    assert resp.status_code == 403
    assert "Agent tokens" in resp.json()["detail"]


@pytest.mark.parametrize("path", [f"{API}/auth/register", f"{API}/auth/login"])
def test_password_auth_endpoints_are_gone(real_client, path):
    resp = real_client.post(path, json={"email": "someone@example.com", "password": "hunter22"})
    assert resp.status_code == 404
