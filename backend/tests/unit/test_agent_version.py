"""Tests for the agent latest-version endpoint."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(db):
    """Create a test client with DB override."""
    from app.database import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_latest_version_returns_version_info(client):
    """GET /agents/latest-version returns version and download URL."""
    with patch("app.api.agents.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            agent_latest_version="1.5.2",
            agent_download_url_macos="https://example.com/rMirror-1.5.2.dmg",
        )
        response = client.get("/v1/agents/latest-version")

    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "1.5.2"
    assert "macos" in data["platforms"]
    assert data["platforms"]["macos"]["url"] == "https://example.com/rMirror-1.5.2.dmg"


def test_latest_version_no_auth_required(client):
    """The latest-version endpoint should be public (no auth required)."""
    with patch("app.api.agents.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock(
            agent_latest_version="1.5.2",
            agent_download_url_macos="https://example.com/rMirror-1.5.2.dmg",
        )
        response = client.get("/v1/agents/latest-version")

    # Should not be 401/403
    assert response.status_code == 200
