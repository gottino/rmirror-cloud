"""Tests for GET /agents/status, in particular ``last_activity_at``."""

from datetime import datetime, timedelta, timezone

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


def test_all_last_synced_null_gives_null(client, db, test_user):
    db.add_all([_notebook(test_user.id, "a", None), _notebook(test_user.id, "b", None)])
    db.commit()

    assert client.get("/v1/agents/status").json()["last_activity_at"] is None


def test_soft_deleted_notebook_still_counts(client, db, test_user):
    """Pins current behaviour: deleted notebooks are not filtered out."""
    deleted = _notebook(test_user.id, "gone", datetime(2026, 11, 22, 8, 0, 0))
    deleted.deleted = True
    db.add_all([deleted, _notebook(test_user.id, "kept", datetime(2026, 11, 1, 8, 0, 0))])
    db.commit()

    assert client.get("/v1/agents/status").json()["last_activity_at"] == "2026-11-22T08:00:00Z"


def test_status_payload_keys_unchanged(client):
    assert set(client.get("/v1/agents/status").json()) == {
        "has_agent_connected",
        "first_connected_at",
        "last_activity_at",
        "onboarding_state",
    }


def test_status_schema_in_openapi(client):
    from app.main import app

    schemas = app.openapi()["components"]["schemas"]
    props = schemas["AgentStatusResponse"]["properties"]
    assert set(props) == {"has_agent_connected", "first_connected_at", "last_activity_at", "onboarding_state"}


def test_utc_iso_formats():
    from app.api.agents import _utc_iso

    assert _utc_iso(None) is None
    assert _utc_iso(datetime(2026, 11, 20, 9, 30)) == "2026-11-20T09:30:00Z"
    aware = datetime(2026, 11, 20, 10, 30, tzinfo=timezone(timedelta(hours=1)))
    assert _utc_iso(aware) == "2026-11-20T10:30:00+01:00"
    assert _utc_iso(datetime(2026, 11, 20, 9, 30, tzinfo=timezone.utc)) == "2026-11-20T09:30:00+00:00"
