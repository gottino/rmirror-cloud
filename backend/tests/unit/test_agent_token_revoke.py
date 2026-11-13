"""Tests for agent token revocation (per-user ``agent_token_version``).

Agent tokens carry the user's ``agent_token_version`` as their ``ver`` claim.
``POST /auth/agent-token/revoke`` (dashboard session only) increments the
version, so every agent token the user holds stops authenticating. Tokens
issued before the claim existed have no ``ver`` and count as version 0.

Minting and revoking need a Clerk session; the tests stand in for it by
overriding ``get_clerk_session_user``. Using the agent token always goes
through the real ``get_clerk_user``.
"""

from datetime import datetime, timedelta
from typing import Generator

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.clerk import get_clerk_session_user
from app.config import get_settings
from app.database import get_db
from app.models.user import User

API = f"/{get_settings().api_version}"
ME = f"{API}/users/me"
MINT = f"{API}/auth/agent-token"
REVOKE = f"{API}/auth/agent-token/revoke"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _legacy_agent_token(user_id: int) -> str:
    """An agent token as issued before revocation existed: no ``ver`` claim."""
    settings = get_settings()
    claims = {
        "sub": str(user_id),
        "type": "agent",
        "exp": datetime.utcnow() + timedelta(days=30),
    }
    return jwt.encode(claims, settings.secret_key, algorithm=settings.algorithm)


def _make_user(db: Session, n: int) -> User:
    user = User(
        email=f"revoke{n}@example.com",
        clerk_user_id=f"clerk_revoke_{n}",
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def alice(db: Session) -> User:
    return _make_user(db, 1)


@pytest.fixture
def bob(db: Session) -> User:
    return _make_user(db, 2)


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    from app.main import app

    def _get_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = _get_db
    try:
        # No ``with`` block: the lifespan (sync worker) must not start.
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_clerk_session_user, None)


def _as_session(user: User) -> None:
    """Make mint/revoke act as a dashboard session of ``user``."""
    from app.main import app

    app.dependency_overrides[get_clerk_session_user] = lambda: user


def _mint(client: TestClient, user: User) -> str:
    _as_session(user)
    resp = client.post(MINT)
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _revoke(client: TestClient, user: User):
    _as_session(user)
    return client.post(REVOKE)


def test_minted_token_carries_current_version(client, alice):
    token = _mint(client, alice)
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims["type"] == "agent"
    assert claims["ver"] == 0
    assert client.get(ME, headers=_auth(token)).status_code == 200


def test_revoke_invalidates_old_token_and_new_token_works(client, db, alice):
    old = _mint(client, alice)
    assert client.get(ME, headers=_auth(old)).status_code == 200

    resp = _revoke(client, alice)
    assert resp.status_code == 200
    assert resp.json() == {"revoked": True}
    db.refresh(alice)
    assert alice.agent_token_version == 1

    assert client.get(ME, headers=_auth(old)).status_code == 401

    new = _mint(client, alice)
    assert jwt.decode(new, options={"verify_signature": False})["ver"] == 1
    assert client.get(ME, headers=_auth(new)).status_code == 200
    assert client.get(ME, headers=_auth(old)).status_code == 401


def test_revoke_twice_invalidates_previous_generation(client, db, alice):
    _revoke(client, alice)
    second = _mint(client, alice)
    assert client.get(ME, headers=_auth(second)).status_code == 200
    _revoke(client, alice)
    db.refresh(alice)
    assert alice.agent_token_version == 2
    assert client.get(ME, headers=_auth(second)).status_code == 401


def test_legacy_token_without_ver_works_until_revoke(client, alice):
    legacy = _legacy_agent_token(alice.id)
    assert client.get(ME, headers=_auth(legacy)).status_code == 200

    assert _revoke(client, alice).status_code == 200

    assert client.get(ME, headers=_auth(legacy)).status_code == 401


def test_revoke_does_not_affect_other_users(client, alice, bob):
    alice_token = _mint(client, alice)
    bob_token = _mint(client, bob)
    bob_legacy = _legacy_agent_token(bob.id)

    assert _revoke(client, alice).status_code == 200

    assert client.get(ME, headers=_auth(alice_token)).status_code == 401
    assert client.get(ME, headers=_auth(bob_token)).status_code == 200
    assert client.get(ME, headers=_auth(bob_legacy)).status_code == 200


@pytest.mark.parametrize("bad_ver", [1, -1, "0", None, 0.5, True])
def test_token_with_mismatched_or_malformed_ver_is_rejected(client, alice, bad_ver):
    settings = get_settings()
    token = jwt.encode(
        {
            "sub": str(alice.id),
            "type": "agent",
            "ver": bad_ver,
            "exp": datetime.utcnow() + timedelta(days=1),
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    assert client.get(ME, headers=_auth(token)).status_code == 401


def test_agent_token_cannot_revoke(client, alice):
    """Revocation is session-only: an agent token gets 403, version unchanged."""
    token = _mint(client, alice)
    from app.main import app

    app.dependency_overrides.pop(get_clerk_session_user, None)
    resp = client.post(REVOKE, headers=_auth(token))
    assert resp.status_code == 403
    assert client.get(ME, headers=_auth(token)).status_code == 200
