"""Tests for the shared, user-keyed rate limiter (app/middleware/rate_limit.py).

These run against the production app (app.main.app) with the real auth
dependencies and real signed tokens, so they check that the limiter key is
read after authentication has recorded the user on ``request.state``.
All TestClient requests come from the same client address ("testclient"),
i.e. every user here is "behind the same IP".
"""

import io
from datetime import datetime, timedelta
from typing import Generator
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from limits import parse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.middleware.rate_limit import (
    DEFAULT_LIMIT,
    UNAUTHENTICATED_LIMIT,
    UPLOAD_LIMIT,
    WEBHOOK_LIMIT,
)
from app.models.user import User

_RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _amount(limit: str) -> int:
    return parse(limit).amount


def _clerk_token(clerk_user_id: str) -> str:
    """An RS256 session token as Clerk would issue it (verified via a fake JWKS)."""
    claims = {"sub": clerk_user_id, "exp": datetime.utcnow() + timedelta(hours=1)}
    return jwt.encode(claims, _RSA_KEY, algorithm="RS256")


def _agent_token(user_id: int) -> str:
    settings = get_settings()
    claims = {
        "sub": str(user_id),
        "type": "agent",
        "exp": datetime.utcnow() + timedelta(days=1),
    }
    return jwt.encode(claims, settings.secret_key, algorithm=settings.algorithm)


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_user(db: Session, n: int) -> User:
    user = User(
        email=f"ratelimit{n}@example.com",
        full_name=f"Rate Limit {n}",
        clerk_user_id=f"clerk_ratelimit_{n}",
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def fake_jwks():
    """Make get_clerk_user verify RS256 tokens against our test key."""
    signing_key = MagicMock()
    signing_key.key = _RSA_KEY.public_key()
    jwks_client = MagicMock()
    jwks_client.get_signing_key_from_jwt.return_value = signing_key
    with patch("app.auth.clerk.get_jwks_client", return_value=jwks_client):
        yield


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
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


def _upload(client: TestClient, token: str):
    # A non-.rm filename is rejected with 400 at the top of the endpoint, after
    # the rate limit was counted, so this is a cheap way to spend the budget.
    files = {"rm_file": ("not-a-page.txt", io.BytesIO(b"x"), "text/plain")}
    return client.post("/v1/processing/rm-file", files=files, headers=_auth(token))


# ---------------------------------------------------------------------------
# Key: authenticated requests are keyed by the user auth resolved
# ---------------------------------------------------------------------------


def test_key_is_user_for_clerk_authenticated_request(db, fake_jwks):
    """get_clerk_user records the user, and the decorator reads it afterwards."""
    from fastapi import Depends, FastAPI, Request

    from app.auth.clerk import get_clerk_active_user
    from app.middleware.rate_limit import (
        get_rate_limit_key,
        install_rate_limiting,
        limiter,
    )

    user = _make_user(db, 1)
    app = FastAPI()
    install_rate_limiting(app)
    seen: dict = {}

    @app.get("/probe")
    @limiter.limit("1000/minute")
    async def probe(request: Request, _user: User = Depends(get_clerk_active_user)):
        return {"ok": True}

    def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db

    real_key = get_rate_limit_key

    def spy(request):
        key = real_key(request)
        seen["key"] = key
        return key

    # Spy on the key the limiter itself computes when the decorated endpoint runs
    with patch.object(limiter._route_limits[f"{__name__}.probe"][0], "key_func", spy):
        resp = TestClient(app).get("/probe", headers=_auth(_clerk_token(user.clerk_user_id)))

    assert resp.status_code == 200
    assert seen["key"] == f"user:{user.id}"


def test_two_users_behind_one_ip_have_independent_upload_budgets(client, db, fake_jwks):
    clerk_user = _make_user(db, 1)
    agent_user = _make_user(db, 2)
    clerk_token = _clerk_token(clerk_user.clerk_user_id)
    agent_token = _agent_token(agent_user.id)
    allowed = _amount(UPLOAD_LIMIT)

    for i in range(allowed):
        resp = _upload(client, clerk_token)
        assert resp.status_code == 400, f"upload {i}: {resp.status_code} {resp.text}"

    assert _upload(client, clerk_token).status_code == 429

    # Same IP, different user: full budget still available
    for i in range(allowed):
        resp = _upload(client, agent_token)
        assert resp.status_code == 400, f"upload {i}: {resp.status_code} {resp.text}"
    assert _upload(client, agent_token).status_code == 429


def test_upload_limit_is_sized_for_initial_sync():
    assert UPLOAD_LIMIT == get_settings().rate_limit_upload
    assert parse(UPLOAD_LIMIT) == parse("120/minute")


# ---------------------------------------------------------------------------
# Default limit: routes without their own decorator are still limited
# ---------------------------------------------------------------------------


def test_unauthenticated_route_without_decorator_hits_default_limit(client):
    allowed = _amount(DEFAULT_LIMIT)
    for i in range(allowed):
        resp = client.get("/")
        assert resp.status_code == 200, f"request {i}: {resp.status_code}"

    resp = client.get("/")
    assert resp.status_code == 429


def test_default_limit_buckets_are_per_endpoint(client):
    """Spending the default budget on one route leaves other routes usable."""
    for _ in range(_amount(DEFAULT_LIMIT) + 1):
        client.get("/")
    assert client.get("/").status_code == 429
    assert client.get("/v1/agents/latest-version").status_code == 200


# ---------------------------------------------------------------------------
# Stricter limits on public routes
# ---------------------------------------------------------------------------


def test_waitlist_signup_has_strict_limit(client):
    allowed = _amount(UNAUTHENTICATED_LIMIT)
    assert allowed < _amount(DEFAULT_LIMIT)
    body = {"email": "waitlist-rl@example.com"}
    with patch("app.utils.email.get_email_service"):
        for i in range(allowed):
            resp = client.post("/v1/waitlist", json=body)
            assert resp.status_code == 201, f"request {i}: {resp.status_code} {resp.text}"
        assert client.post("/v1/waitlist", json=body).status_code == 429


def test_clerk_webhook_has_strict_limit(client):
    allowed = _amount(WEBHOOK_LIMIT)
    assert allowed < _amount(DEFAULT_LIMIT)
    for _ in range(allowed):
        resp = client.post("/v1/webhooks/clerk", content=b"{}")
        assert resp.status_code != 429
    assert client.post("/v1/webhooks/clerk", content=b"{}").status_code == 429
