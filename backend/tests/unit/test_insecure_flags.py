"""Tests for the explicit insecure development flags and Clerk claim checks.

DEBUG only controls non-security behaviour. Each relaxed security check has
its own flag (ALLOW_UNVERIFIED_CLERK_TOKENS, ALLOW_UNSIGNED_WEBHOOKS,
DISABLE_TLS_VERIFY), refused at start-up outside SQLite. Clerk session tokens
are checked for issuer (``iss``) and authorised party (``azp``).
"""

import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings, check_insecure_flags, get_settings
from app.database import get_db
from app.models.user import User

_RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_POSTGRES_URL = "postgresql://user:pass@localhost:5432/rmirror"
_ISSUER = "https://clerk.example.test"
_JWKS_URL = f"{_ISSUER}/.well-known/jwks.json"
_BACKEND_DIR = Path(__file__).resolve().parents[2]


def _settings(**overrides) -> Settings:
    """The test settings with the given fields replaced."""
    return get_settings().model_copy(update=overrides)


# ---------------------------------------------------------------------------
# Settings and start-up guard
# ---------------------------------------------------------------------------


def test_insecure_flags_default_off():
    settings = Settings(secret_key="x", database_url="sqlite:///:memory:")
    assert settings.allow_unverified_clerk_tokens is False
    assert settings.allow_unsigned_webhooks is False
    assert settings.disable_tls_verify is False


def test_guard_allows_flags_with_sqlite_and_warns(caplog):
    settings = _settings(
        database_url="sqlite:///./rmirror.db",
        allow_unverified_clerk_tokens=True,
        disable_tls_verify=True,
    )
    with caplog.at_level(logging.WARNING, logger="app.config"):
        check_insecure_flags(settings)
    text = caplog.text
    assert "ALLOW_UNVERIFIED_CLERK_TOKENS" in text
    assert "DISABLE_TLS_VERIFY" in text
    assert "ALLOW_UNSIGNED_WEBHOOKS" not in text


@pytest.mark.parametrize(
    "field,name",
    [
        ("allow_unverified_clerk_tokens", "ALLOW_UNVERIFIED_CLERK_TOKENS"),
        ("allow_unsigned_webhooks", "ALLOW_UNSIGNED_WEBHOOKS"),
        ("disable_tls_verify", "DISABLE_TLS_VERIFY"),
    ],
)
def test_guard_refuses_each_flag_with_postgres(field, name):
    settings = _settings(database_url=_POSTGRES_URL, **{field: True})
    with pytest.raises(RuntimeError) as exc:
        check_insecure_flags(settings)
    assert name in str(exc.value)
    assert "SQLite" in str(exc.value)


def test_guard_names_every_enabled_flag():
    settings = _settings(
        database_url=_POSTGRES_URL,
        allow_unverified_clerk_tokens=True,
        allow_unsigned_webhooks=True,
        disable_tls_verify=True,
    )
    with pytest.raises(RuntimeError) as exc:
        check_insecure_flags(settings)
    for name in (
        "ALLOW_UNVERIFIED_CLERK_TOKENS",
        "ALLOW_UNSIGNED_WEBHOOKS",
        "DISABLE_TLS_VERIFY",
    ):
        assert name in str(exc.value)


def test_guard_accepts_postgres_without_flags_even_with_debug():
    check_insecure_flags(_settings(database_url=_POSTGRES_URL, debug=True))


def _import_main(extra_env: dict) -> subprocess.CompletedProcess:
    env = {**os.environ, "SECRET_KEY": "test-secret-key", **extra_env}
    for key in ("ALLOW_UNVERIFIED_CLERK_TOKENS", "ALLOW_UNSIGNED_WEBHOOKS", "DISABLE_TLS_VERIFY"):
        env.setdefault(key, "false")
    return subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=_BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_app_start_refuses_insecure_flag_with_postgres():
    result = _import_main(
        {"DATABASE_URL": _POSTGRES_URL, "ALLOW_UNSIGNED_WEBHOOKS": "true"}
    )
    assert result.returncode != 0
    assert "RuntimeError" in result.stderr
    assert "ALLOW_UNSIGNED_WEBHOOKS" in result.stderr


def test_app_start_allows_insecure_flag_with_sqlite():
    result = _import_main(
        {"DATABASE_URL": "sqlite:///:memory:", "ALLOW_UNSIGNED_WEBHOOKS": "true"}
    )
    assert result.returncode == 0, result.stderr


def test_authorized_parties_default_to_cors_and_dashboard_origins():
    settings = Settings(
        secret_key="x",
        cors_origins=["http://localhost:3000", "http://localhost:5555/"],
        dashboard_url="https://dashboard.example.test/some/path",
    )
    assert settings.clerk_authorized_parties == [
        "http://localhost:3000",
        "http://localhost:5555",
        "https://dashboard.example.test",
    ]


def test_authorized_parties_env_is_a_json_list(monkeypatch):
    monkeypatch.setenv(
        "CLERK_AUTHORIZED_PARTIES", '["https://a.example.test","https://b.example.test"]'
    )
    settings = Settings(secret_key="x")
    assert settings.clerk_authorized_parties == [
        "https://a.example.test",
        "https://b.example.test",
    ]


# ---------------------------------------------------------------------------
# Clerk token checks (get_clerk_user)
# ---------------------------------------------------------------------------


@pytest.fixture
def clerk_user(db: Session) -> User:
    user = User(
        email="flags@example.com",
        full_name="Flags",
        clerk_user_id="clerk_flags_user",
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def probe(db: Session) -> Generator[TestClient, None, None]:
    from app.auth.clerk import get_clerk_active_user

    app = FastAPI()

    @app.get("/probe")
    async def _probe(user: User = Depends(get_clerk_active_user)):
        return {"id": user.id}

    def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)


@pytest.fixture
def fake_jwks():
    signing_key = MagicMock()
    signing_key.key = _RSA_KEY.public_key()
    jwks_client = MagicMock()
    jwks_client.get_signing_key_from_jwt.return_value = signing_key
    with patch("app.auth.clerk.get_jwks_client", return_value=jwks_client):
        yield


def _signed(sub: str, **claims) -> str:
    payload = {"sub": sub, "exp": datetime.utcnow() + timedelta(hours=1), **claims}
    return jwt.encode(payload, _RSA_KEY, algorithm="RS256")


def _unsigned(sub: str) -> str:
    """A Clerk-shaped RS256 token signed with a key the server does not know."""
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    payload = {"sub": sub, "exp": datetime.utcnow() + timedelta(hours=1)}
    return jwt.encode(payload, other, algorithm="RS256")


def _get(client: TestClient, token: str, **settings_overrides):
    settings = _settings(**settings_overrides)
    with patch("app.auth.clerk.get_settings", return_value=settings):
        return client.get("/probe", headers={"Authorization": f"Bearer {token}"})


def test_unverified_token_rejected_with_debug_and_postgres(probe, clerk_user):
    resp = _get(
        probe,
        _unsigned(clerk_user.clerk_user_id),
        debug=True,
        database_url=_POSTGRES_URL,
        clerk_jwks_url=None,
        clerk_issuer=None,
        allow_unverified_clerk_tokens=False,
    )
    assert resp.status_code == 401


def test_unverified_token_accepted_with_flag(probe, clerk_user):
    resp = _get(
        probe,
        _unsigned(clerk_user.clerk_user_id),
        clerk_jwks_url=None,
        clerk_issuer=None,
        allow_unverified_clerk_tokens=True,
    )
    assert resp.status_code == 200
    assert resp.json() == {"id": clerk_user.id}


def test_issuer_derived_from_jwks_url_accepts_matching_iss(probe, clerk_user, fake_jwks):
    token = _signed(clerk_user.clerk_user_id, iss=_ISSUER)
    resp = _get(probe, token, clerk_jwks_url=_JWKS_URL, clerk_issuer=None)
    assert resp.status_code == 200


@pytest.mark.parametrize("iss", ["https://other.example.test", None])
def test_issuer_derived_from_jwks_url_rejects_wrong_or_missing_iss(
    probe, clerk_user, fake_jwks, iss
):
    claims = {"iss": iss} if iss else {}
    token = _signed(clerk_user.clerk_user_id, **claims)
    resp = _get(probe, token, clerk_jwks_url=_JWKS_URL, clerk_issuer=None)
    assert resp.status_code == 401


def test_explicit_clerk_issuer_wins(probe, clerk_user, fake_jwks):
    explicit = "https://issuer.example.test"
    ok = _signed(clerk_user.clerk_user_id, iss=explicit)
    derived = _signed(clerk_user.clerk_user_id, iss=_ISSUER)
    assert _get(probe, ok, clerk_jwks_url=_JWKS_URL, clerk_issuer=explicit).status_code == 200
    assert _get(probe, derived, clerk_jwks_url=_JWKS_URL, clerk_issuer=explicit).status_code == 401


def test_issuer_check_skipped_when_jwks_url_has_other_shape(probe, clerk_user, fake_jwks):
    token = _signed(clerk_user.clerk_user_id, iss="https://anything.example.test")
    resp = _get(
        probe, token, clerk_jwks_url="https://jwks.example.test/v1/jwks", clerk_issuer=None
    )
    assert resp.status_code == 200


@pytest.mark.parametrize(
    "iss,expected", [(_ISSUER, 200), ("https://other.example.test", 401)]
)
def test_issuer_check_applies_to_unverified_dev_tokens_when_configured(
    probe, clerk_user, iss, expected
):
    token = _signed(clerk_user.clerk_user_id, iss=iss)
    resp = _get(
        probe,
        token,
        clerk_jwks_url=None,
        clerk_issuer=_ISSUER,
        allow_unverified_clerk_tokens=True,
    )
    assert resp.status_code == expected


def test_azp_in_allowed_parties_accepted(probe, clerk_user, fake_jwks):
    token = _signed(clerk_user.clerk_user_id, iss=_ISSUER, azp="https://dash.example.test")
    resp = _get(
        probe,
        token,
        clerk_jwks_url=_JWKS_URL,
        clerk_authorized_parties=["https://dash.example.test"],
    )
    assert resp.status_code == 200


def test_azp_not_in_allowed_parties_rejected(probe, clerk_user, fake_jwks):
    token = _signed(clerk_user.clerk_user_id, iss=_ISSUER, azp="https://evil.example.test")
    resp = _get(
        probe,
        token,
        clerk_jwks_url=_JWKS_URL,
        clerk_authorized_parties=["https://dash.example.test"],
    )
    assert resp.status_code == 401


def test_token_without_azp_accepted(probe, clerk_user, fake_jwks):
    token = _signed(clerk_user.clerk_user_id, iss=_ISSUER)
    resp = _get(
        probe,
        token,
        clerk_jwks_url=_JWKS_URL,
        clerk_authorized_parties=["https://dash.example.test"],
    )
    assert resp.status_code == 200


def test_azp_default_list_accepts_dashboard_origin(probe, clerk_user, fake_jwks):
    settings = Settings(
        secret_key="test-secret-key",
        database_url="sqlite:///:memory:",
        clerk_jwks_url=_JWKS_URL,
        dashboard_url="https://dash.example.test",
    )
    token = _signed(clerk_user.clerk_user_id, iss=_ISSUER, azp="https://dash.example.test")
    with patch("app.auth.clerk.get_settings", return_value=settings):
        resp = probe.get("/probe", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_unknown_user_gets_404_not_401(probe, fake_jwks):
    token = _signed("clerk_nobody_has_this_id")
    resp = _get(probe, token, clerk_jwks_url=None, clerk_issuer=None)
    assert resp.status_code == 404
    assert "User not found" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------


def _post_webhook(**settings_overrides):
    from app.main import app

    settings = _settings(clerk_webhook_secret=None, **settings_overrides)
    with patch("app.api.webhooks.clerk.get_settings", return_value=settings):
        return TestClient(app).post(
            "/v1/webhooks/clerk", json={"type": "unknown.event", "data": {}}
        )


def test_unsigned_webhook_refused_even_with_debug():
    resp = _post_webhook(debug=True, allow_unsigned_webhooks=False)
    assert resp.status_code == 500


def test_unsigned_webhook_accepted_with_flag():
    resp = _post_webhook(allow_unsigned_webhooks=True)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# TLS verification for Notion calls
# ---------------------------------------------------------------------------


def _notion_service(**overrides):
    from app.services.notion_oauth import NotionOAuthService

    settings = _settings(**overrides)
    with patch("app.services.notion_oauth.get_settings", return_value=settings):
        return NotionOAuthService(), settings


@pytest.mark.parametrize(
    "overrides,expected_verify",
    [
        ({"debug": True, "disable_tls_verify": False}, True),
        ({"disable_tls_verify": True}, False),
    ],
)
def test_notion_http_client_tls_verification(overrides, expected_verify):
    service, _ = _notion_service(**overrides)
    with patch("app.services.notion_oauth.httpx.Client") as client_cls:
        service._get_http_client()
    assert client_cls.call_args.kwargs["verify"] is expected_verify


@pytest.mark.parametrize(
    "overrides,expected_verify",
    [
        ({"debug": True, "disable_tls_verify": False}, True),
        ({"disable_tls_verify": True}, False),
    ],
)
@pytest.mark.asyncio
async def test_notion_token_exchange_tls_verification(
    overrides, expected_verify, mock_httpx_async_client
):
    import httpx

    service, settings = _notion_service(**overrides)
    with patch("app.services.notion_oauth.get_settings", return_value=settings):
        await service.exchange_code_for_token("code")
    assert httpx.AsyncClient.call_args.kwargs["verify"] is expected_verify
