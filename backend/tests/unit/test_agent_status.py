"""Tests for GET /agents/status, in particular ``last_activity_at``."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth.clerk import get_clerk_active_user
from app.models.notebook import Notebook


@pytest.fixture
def client(db, test_user):
    from app.database import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_clerk_active_user] = lambda: test_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _notebook(user_id: int, uuid: str, last_synced_at: datetime | None) -> Notebook:
    return Notebook(
        user_id=user_id,
        notebook_uuid=uuid,
        visible_name=uuid,
        document_type="notebook",
        last_synced_at=last_synced_at,
    )


def test_status_without_notebooks_has_no_activity(client, test_user):
    response = client.get("/v1/agents/status")

    assert response.status_code == 200
    data = response.json()
    assert data["has_agent_connected"] is False
    assert data["last_activity_at"] is None


def test_last_activity_is_newest_notebook_sync_in_utc(client, db, test_user, fresh_user):
    newest = datetime(2026, 11, 20, 9, 30, 0)
    test_user.agent_first_connected_at = newest - timedelta(days=10)
    db.add_all(
        [
            _notebook(test_user.id, "old", newest - timedelta(days=3)),
            _notebook(test_user.id, "new", newest),
            _notebook(test_user.id, "never", None),
            # Another user's newer upload must not count.
            _notebook(fresh_user.id, "other", newest + timedelta(days=1)),
        ]
    )
    db.commit()

    data = client.get("/v1/agents/status").json()

    assert data["has_agent_connected"] is True
    assert data["last_activity_at"] == "2026-11-20T09:30:00Z"
