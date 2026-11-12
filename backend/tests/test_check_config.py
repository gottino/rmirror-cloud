"""Tests for scripts/check_config.py, the deploy-time config check."""

import importlib.util
from pathlib import Path

import pytest

from app.config import get_settings

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_config.py"

FULL_ENV = {
    "DATABASE_URL": "postgresql://user:pw@localhost:5432/rmirror",
    "SECRET_KEY": "sk-value-1",
    "CLERK_JWKS_URL": "https://clerk.example.invalid/.well-known/jwks.json",
    "CLERK_SECRET_KEY": "clerk-secret-value",
    "CLERK_WEBHOOK_SECRET": "whsec-value",
    "GOOGLE_AI_API_KEY": "google-key-value",
    "INTEGRATION_MASTER_KEY": "master-key-value",
    "S3_ENDPOINT_URL": "https://s3.example.invalid",
    "S3_ACCESS_KEY": "s3-access-value",
    "S3_SECRET_KEY": "s3-secret-value",
    "S3_BUCKET_NAME": "bucket-value",
}


@pytest.fixture
def check_config():
    spec = importlib.util.spec_from_file_location("check_config", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def run_main(check_config, monkeypatch, tmp_path, capsys):
    """Run main() with exactly the given environment and no .env file."""

    def _run(env):
        monkeypatch.chdir(tmp_path)  # no .env here
        for name in list(FULL_ENV) + ["POSTGRES_USER"]:
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        get_settings.cache_clear()
        try:
            code = check_config.main()
        finally:
            get_settings.cache_clear()
        return code, capsys.readouterr().out

    return _run


def test_complete_config_passes(run_main):
    code, out = run_main(FULL_ENV)
    assert code == 0
    assert "OK" in out


@pytest.mark.parametrize("name", [n for n in FULL_ENV if n not in ("DATABASE_URL", "SECRET_KEY")])
def test_each_missing_key_fails_and_is_named(run_main, name):
    env = {k: v for k, v in FULL_ENV.items() if k != name}
    if name == "S3_BUCKET_NAME":
        env[name] = ""  # has a non-empty default; an empty value must fail
    code, out = run_main(env)
    assert code == 1
    assert name in out


def test_empty_value_counts_as_missing(run_main):
    code, out = run_main({**FULL_ENV, "GOOGLE_AI_API_KEY": "  "})
    assert code == 1
    assert "GOOGLE_AI_API_KEY" in out


def test_sqlite_database_fails(run_main):
    code, out = run_main({**FULL_ENV, "DATABASE_URL": "sqlite:///./rmirror.db"})
    assert code == 1
    assert "DATABASE_URL" in out


def test_missing_database_url_falls_back_to_sqlite_and_fails(run_main):
    env = {k: v for k, v in FULL_ENV.items() if k != "DATABASE_URL"}
    code, out = run_main(env)
    assert code == 1
    assert "DATABASE_URL" in out


def test_missing_secret_key_fails_without_traceback(run_main):
    env = {k: v for k, v in FULL_ENV.items() if k != "SECRET_KEY"}
    code, out = run_main(env)
    assert code == 1
    assert "SECRET_KEY" in out


def test_values_are_never_printed(run_main):
    env = {k: v for k, v in FULL_ENV.items() if k not in ("CLERK_SECRET_KEY", "SECRET_KEY")}
    code, out = run_main(env)
    assert code == 1
    for value in FULL_ENV.values():
        assert value not in out
