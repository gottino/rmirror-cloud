"""The interactive API docs (/docs, /redoc, /openapi.json) are off unless enabled."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import api_docs_kwargs

DOC_PATHS = ["/docs", "/redoc", "/openapi.json"]


def _client(enable_api_docs: bool) -> TestClient:
    settings = Settings(enable_api_docs=enable_api_docs)
    app = FastAPI(**api_docs_kwargs(settings))

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    return TestClient(app)


def test_api_docs_disabled_by_default():
    assert Settings().enable_api_docs is False


@pytest.mark.parametrize("path", DOC_PATHS)
def test_doc_routes_return_404_when_disabled(path):
    client = _client(enable_api_docs=False)
    assert client.get(path).status_code == 404
    # The app itself still works
    assert client.get("/ping").status_code == 200


@pytest.mark.parametrize("path", DOC_PATHS)
def test_doc_routes_served_when_enabled(path):
    assert _client(enable_api_docs=True).get(path).status_code == 200


def test_enable_api_docs_reads_environment(monkeypatch):
    monkeypatch.setenv("ENABLE_API_DOCS", "true")
    assert Settings().enable_api_docs is True


def test_production_app_has_no_doc_routes():
    """app.main.app, built with default settings, exposes no docs routes."""
    from app.main import app

    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None
    client = TestClient(app)
    for path in DOC_PATHS:
        assert client.get(path).status_code == 404
