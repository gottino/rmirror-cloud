"""Tests for the start-up configuration check and the storage fallback rule."""

import logging

import pytest

from app import dependencies
from app.config import Settings, config_problems, validate_startup

FULL = {
    "secret_key": "sk-value-1",
    "clerk_jwks_url": "https://clerk.example.invalid/jwks.json",
    "clerk_secret_key": "clerk-secret-value",
    "clerk_webhook_secret": "whsec-value",
    "google_ai_api_key": "google-key-value",
    "integration_master_key": "master-key-value",
    "s3_endpoint_url": "https://s3.example.invalid",
    "s3_access_key": "s3-access-value",
    "s3_secret_key": "s3-secret-value",
}


def make(**overrides):
    values = {**FULL, "storage_backend": None, **overrides}
    return Settings(_env_file=None, debug=values.pop("debug", False), **values)


def test_full_config_has_nothing_missing():
    missing, _ = config_problems(make())
    assert missing == []


def test_missing_gemini_key_fails_outside_debug_and_is_named():
    with pytest.raises(RuntimeError) as exc:
        validate_startup(make(google_ai_api_key=None), logging.getLogger("t"))
    assert "GOOGLE_AI_API_KEY" in str(exc.value)


def test_every_missing_name_is_listed_in_one_message():
    settings = make(google_ai_api_key=None, clerk_secret_key="", s3_access_key=None)
    with pytest.raises(RuntimeError) as exc:
        validate_startup(settings, logging.getLogger("t"))
    for name in ("GOOGLE_AI_API_KEY", "CLERK_SECRET_KEY", "S3_ACCESS_KEY"):
        assert name in str(exc.value)


def test_values_are_never_in_the_message():
    with pytest.raises(RuntimeError) as exc:
        validate_startup(make(google_ai_api_key=None), logging.getLogger("t"))
    for value in FULL.values():
        assert value not in str(exc.value)


def test_debug_warns_and_continues(caplog):
    with caplog.at_level(logging.WARNING):
        validate_startup(make(debug=True, google_ai_api_key=None), logging.getLogger("t"))
    assert "GOOGLE_AI_API_KEY" in caplog.text


def test_local_storage_needs_explicit_choice():
    no_s3 = {"s3_endpoint_url": None, "s3_access_key": None, "s3_secret_key": None}
    missing, _ = config_problems(make(**no_s3))
    assert "S3_ENDPOINT_URL" in missing
    missing, _ = config_problems(make(storage_backend="local", **no_s3))
    assert missing == []


def test_unknown_storage_backend_is_rejected():
    missing, _ = config_problems(make(storage_backend="floppy"))
    assert any(m.startswith("STORAGE_BACKEND") for m in missing)


def test_partial_integration_config_fails_and_unset_only_warns():
    missing, warnings = config_problems(make())
    assert missing == []
    assert any("Notion" in w for w in warnings)
    assert any("RESEND_API_KEY" in w for w in warnings)
    missing, _ = config_problems(make(notion_client_id="id"))
    assert "NOTION_CLIENT_SECRET" in missing
    assert "NOTION_REDIRECT_URI" in missing


def _storage(monkeypatch, **overrides):
    monkeypatch.setattr(dependencies, "settings", make(**overrides))
    dependencies.get_storage_service.cache_clear()
    try:
        return dependencies.get_storage_service()
    finally:
        dependencies.get_storage_service.cache_clear()


NO_S3 = {"s3_endpoint_url": None, "s3_access_key": None, "s3_secret_key": None}


def test_storage_refuses_local_fallback_outside_debug(monkeypatch):
    with pytest.raises(RuntimeError, match="STORAGE_BACKEND=local"):
        _storage(monkeypatch, **NO_S3)


def test_storage_local_when_explicit_or_debug(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert type(_storage(monkeypatch, storage_backend="local", **NO_S3)).__name__ == "LocalStorageService"
    assert type(_storage(monkeypatch, debug=True, **NO_S3)).__name__ == "LocalStorageService"


def test_storage_uses_s3_when_configured(monkeypatch):
    monkeypatch.setattr(dependencies, "S3StorageService", lambda: "s3")
    assert _storage(monkeypatch) == "s3"
