"""One code path writes to Notion: the sync worker, fed by the sync queue.

Covers the target registry, the upload enqueue loop consulting capabilities,
/sync/trigger and /processing/metadata/update enqueuing instead of writing
inline, the worker's notebook_metadata handler, and the removal of the old
whole-notebook writer.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.clerk import get_clerk_active_user, get_clerk_session_user
from app.core.sync_engine import SyncItem, SyncResult
from app.integrations import registry
from app.models.notebook import Notebook
from app.models.notebook_page import NotebookPage
from app.models.page import OcrStatus, Page
from app.models.sync_record import (
    IntegrationConfig,
    SyncItemType,
    SyncQueue,
    SyncRecord,
    SyncStatus,
)
from tests.conftest import create_user_with_quota
from tests.test_config import test_app  # noqa: F401 - fixture

API = "/v1"
NB_UUID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
PAGE_UUID = "0b6d1f9e-2c55-4a39-9f5e-1d2b3c4d5e6f"


@pytest.fixture
def user(db: Session):
    return create_user_with_quota(db, used=0, limit=30)


@pytest.fixture(autouse=True)
def plain_configs():
    """Test configs are stored unencrypted; read them as plain JSON."""
    with patch.object(
        IntegrationConfig, "get_config", lambda self: json.loads(self.config_encrypted)
    ):
        yield


def _config(db, user, target_name, config='{"access_token": "t", "database_id": "d"}'):
    cfg = IntegrationConfig(
        user_id=user.id,
        target_name=target_name,
        is_enabled=True,
        config_encrypted=config,
    )
    db.add(cfg)
    db.commit()
    return cfg


@pytest.fixture
def notebook_with_page(db: Session, user):
    nb = Notebook(
        notebook_uuid=NB_UUID,
        user_id=user.id,
        visible_name="Writer Test",
        document_type="notebook",
        created_at=datetime.utcnow(),
    )
    db.add(nb)
    db.commit()
    page = Page(
        notebook_id=nb.id,
        page_uuid=PAGE_UUID,
        ocr_status=OcrStatus.COMPLETED,
        ocr_text="Some handwriting",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(page)
    db.commit()
    db.add(NotebookPage(notebook_id=nb.id, page_id=page.id, page_number=1))
    db.commit()
    db.refresh(nb)
    db.refresh(page)
    return nb, page


@pytest.fixture
def client(db, user, test_app, reset_rate_limiter):  # noqa: F811
    async def _user():
        return user

    test_app.dependency_overrides[get_clerk_active_user] = _user
    test_app.dependency_overrides[get_clerk_session_user] = _user
    with TestClient(test_app) as c:
        yield c
    test_app.dependency_overrides.pop(get_clerk_active_user, None)
    test_app.dependency_overrides.pop(get_clerk_session_user, None)


# --- registry -------------------------------------------------------------


def test_registry_capabilities():
    assert registry.supports("notion", "page_text")
    assert registry.supports("notion", "notebook_metadata")
    assert not registry.supports("todoist", "page_text")
    assert not registry.supports("notion-todos", "page_text")
    assert not registry.supports("obsidian", "page_text")
    assert not registry.supports("unknown", "page_text")
    assert registry.targets_supporting("todo") == ["notion-todos", "todoist"]
    assert registry.targets_supporting("page_text") == ["notion"]


def test_registry_create_target_unknown_or_pull_based():
    with pytest.raises(ValueError):
        registry.create_target("unknown", {})
    with pytest.raises(ValueError):
        registry.create_target("obsidian", {})


# --- upload enqueue loop ----------------------------------------------------


def test_enqueue_skips_targets_without_page_text(db, user, notebook_with_page):
    from app.services.page_events import enqueue_integration_syncs

    nb, page = notebook_with_page
    for name in ("notion", "todoist", "notion-todos", "obsidian"):
        _config(db, user, name)

    assert enqueue_integration_syncs(db, page, nb) == 1
    rows = db.query(SyncQueue).filter(SyncQueue.item_type == "page_text").all()
    assert [r.target_name for r in rows] == ["notion"]


def test_enqueue_consults_registry_capabilities(db, user, notebook_with_page, monkeypatch):
    from app.services.page_events import enqueue_integration_syncs

    nb, page = notebook_with_page
    _config(db, user, "notion")
    _config(db, user, "custom")
    monkeypatch.setitem(
        registry._TARGETS,
        "custom",
        registry.TargetSpec(name="custom", factory=None, item_types=frozenset({"page_text"})),
    )
    monkeypatch.setitem(
        registry._TARGETS,
        "notion",
        registry.TargetSpec(name="notion", factory=None, item_types=frozenset({"todo"})),
    )

    enqueue_integration_syncs(db, page, nb)
    rows = db.query(SyncQueue).filter(SyncQueue.item_type == "page_text").all()
    assert [r.target_name for r in rows] == ["custom"]


# --- routes -------------------------------------------------------------------


def test_process_queue_route_removed():
    from fastapi.routing import APIRoute

    from app.main import app

    paths = {r.path for r in app.routes if isinstance(r, APIRoute)}
    assert not any(p.endswith("/sync/process-queue") for p in paths)
    assert f"{API}/sync/trigger" in paths


def test_trigger_enqueues_page_text_without_writing(client, db, user, notebook_with_page):
    _config(db, user, "notion")
    _, page = notebook_with_page

    with patch("app.integrations.notion_sync.NotionClient") as notion, \
         patch("app.integrations.notion_sync.httpx.post") as post:
        resp = client.post(f"{API}/sync/trigger", json={"target_name": "notion"})
        notion.assert_not_called()
        post.assert_not_called()

    assert resp.status_code == 200, resp.text
    rows = db.query(SyncQueue).filter(SyncQueue.user_id == user.id).all()
    assert len(rows) == 1
    assert rows[0].item_type == "page_text"
    assert rows[0].target_name == "notion"
    assert rows[0].page_uuid == PAGE_UUID
    assert rows[0].item_id == str(page.id)
    assert rows[0].status == "pending"

    # A second trigger does not duplicate the pending row.
    resp = client.post(f"{API}/sync/trigger", json={"target_name": "all"})
    assert resp.status_code == 200, resp.text
    assert db.query(SyncQueue).filter(SyncQueue.user_id == user.id).count() == 1


def test_trigger_limits_to_requested_notebooks(client, db, user, notebook_with_page):
    _config(db, user, "notion")
    resp = client.post(
        f"{API}/sync/trigger",
        json={"target_name": "notion", "notebook_uuids": ["00000000-0000-4000-8000-000000000000"]},
    )
    assert resp.status_code == 200, resp.text
    assert db.query(SyncQueue).count() == 0


def test_trigger_rejects_todo_only_target(client, db, user, notebook_with_page):
    _config(db, user, "todoist", config='{"access_token": "t"}')
    resp = client.post(f"{API}/sync/trigger", json={"target_name": "todoist"})
    assert resp.status_code == 400
    assert db.query(SyncQueue).count() == 0


def test_metadata_update_enqueues_instead_of_writing(client, db, user):
    _config(db, user, "notion")
    _config(db, user, "todoist", config='{"access_token": "t"}')

    with patch("app.integrations.notion_sync.NotionClient") as notion, \
         patch("app.integrations.notion_sync.httpx.post") as post:
        resp = client.post(
            f"{API}/processing/metadata/update",
            json={"notebook_uuid": NB_UUID, "visible_name": "Renamed"},
        )
        notion.assert_not_called()
        post.assert_not_called()

    assert resp.status_code == 200, resp.text
    rows = db.query(SyncQueue).filter(SyncQueue.user_id == user.id).all()
    assert [(r.item_type, r.target_name) for r in rows] == [("notebook_metadata", "notion")]
    assert rows[0].notebook_uuid == NB_UUID
    assert rows[0].item_id == NB_UUID
    assert db.query(SyncRecord).count() == 0


def test_metadata_update_skips_enqueue_when_quota_exhausted(client, db, user):
    _config(db, user, "notion")
    with patch(
        "app.api.processing.quota_service.get_quota_status",
        return_value={"is_exhausted": True},
    ):
        resp = client.post(
            f"{API}/processing/metadata/update",
            json={"notebook_uuid": NB_UUID, "visible_name": "Renamed"},
        )
    assert resp.status_code == 200, resp.text
    assert db.query(SyncQueue).count() == 0


# --- worker -------------------------------------------------------------------


def _metadata_row(db, user, nb):
    row = SyncQueue(
        user_id=user.id,
        item_type="notebook_metadata",
        item_id=nb.notebook_uuid,
        content_hash="meta-hash",
        notebook_uuid=nb.notebook_uuid,
        target_name="notion",
        status="processing",
        priority=5,
        scheduled_at=datetime.utcnow() - timedelta(minutes=1),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.mark.asyncio
async def test_worker_processes_notebook_metadata(db, user, notebook_with_page):
    from app.services.sync_worker import SyncWorker

    nb, _ = notebook_with_page
    nb.full_path = "Work/Writer Test"
    db.commit()
    _config(db, user, "notion")
    row = _metadata_row(db, user, nb)

    target = MagicMock()
    target.sync_item = AsyncMock(
        return_value=SyncResult(status=SyncStatus.SUCCESS, target_id="notion-nb-page")
    )
    with patch("app.integrations.registry.NotionSyncTarget", return_value=target):
        await SyncWorker()._process_queue_item(db, row)

    db.refresh(row)
    assert row.status == "completed"
    item: SyncItem = target.sync_item.call_args.args[0]
    assert item.item_type == SyncItemType.NOTEBOOK_METADATA
    assert item.data["notebook_uuid"] == NB_UUID
    assert item.data["title"] == "Writer Test"
    assert item.data["full_path"] == "Work/Writer Test"

    record = db.query(SyncRecord).filter(SyncRecord.item_type == "notebook_metadata").one()
    assert record.notebook_uuid == NB_UUID
    assert record.external_id == "notion-nb-page"
    assert record.content_hash == item.content_hash
    assert record.page_uuid is None

    # A second success for the same notebook updates the one record.
    row2 = _metadata_row(db, user, nb)
    with patch("app.integrations.registry.NotionSyncTarget", return_value=target):
        await SyncWorker()._process_queue_item(db, row2)
    assert db.query(SyncRecord).filter(SyncRecord.item_type == "notebook_metadata").count() == 1


@pytest.mark.asyncio
async def test_worker_metadata_skipped_until_notebook_page_exists(db, user, notebook_with_page):
    from app.services.sync_worker import SyncWorker

    nb, _ = notebook_with_page
    _config(db, user, "notion")
    row = _metadata_row(db, user, nb)

    target = MagicMock()
    target.sync_item = AsyncMock(
        return_value=SyncResult(status=SyncStatus.SKIPPED, metadata={"reason": "not yet synced"})
    )
    with patch("app.integrations.registry.NotionSyncTarget", return_value=target):
        await SyncWorker()._process_queue_item(db, row)

    db.refresh(row)
    assert row.status == "completed"
    assert db.query(SyncRecord).count() == 0


@pytest.mark.asyncio
async def test_worker_rejects_item_type_target_does_not_accept(db, user, notebook_with_page):
    from app.services.sync_worker import SyncWorker

    _, page = notebook_with_page
    _config(db, user, "todoist", config='{"access_token": "t"}')
    row = SyncQueue(
        user_id=user.id,
        item_type="page_text",
        item_id=str(page.id),
        content_hash="h",
        page_uuid=PAGE_UUID,
        notebook_uuid=NB_UUID,
        page_number=1,
        target_name="todoist",
        status="processing",
        priority=3,
        scheduled_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()

    with patch("app.integrations.registry.TodoistSyncTarget") as todoist:
        await SyncWorker()._process_queue_item(db, row)
        todoist.assert_not_called()

    db.refresh(row)
    assert row.status == "failed"


# --- Notion target --------------------------------------------------------------


def test_notion_target_has_no_whole_notebook_writer():
    from app.integrations.notion_sync import NotionSyncTarget

    for name in ("_sync_notebook", "_update_notion_page", "_build_page_blocks"):
        assert not hasattr(NotionSyncTarget, name), name


@pytest.mark.asyncio
async def test_notion_target_rejects_notebook_items(sample_notebook_sync_item):
    with patch("app.integrations.notion_sync.NotionClient") as notion_class, \
         patch("app.integrations.notion_sync.httpx.post") as post:
        client = MagicMock()
        notion_class.return_value = client
        from app.integrations.notion_sync import NotionSyncTarget

        target = NotionSyncTarget(access_token="t", database_id="db")
        result = await target.sync_item(sample_notebook_sync_item)

    assert result.status == SyncStatus.FAILED
    post.assert_not_called()
    client.pages.create.assert_not_called()
    client.pages.update.assert_not_called()
    client.blocks.children.append.assert_not_called()


# --- metadata fingerprint & integrations API ------------------------------------------


def test_identical_metadata_of_two_notebooks_queues_both(db, user):
    from app.services.sync_queue import queue_notebook_metadata_sync

    _config(db, user, "notion")
    notebooks = []
    for nb_uuid in (NB_UUID, "00000000-0000-4000-8000-000000000001"):
        nb = Notebook(
            notebook_uuid=nb_uuid, user_id=user.id, visible_name="Same", document_type="notebook"
        )
        db.add(nb)
        notebooks.append(nb)
    db.commit()

    rows = [row for nb in notebooks for row in queue_notebook_metadata_sync(db, nb)]
    assert len({row.id for row in rows}) == 2
    assert {row.notebook_uuid for row in rows} == {nb.notebook_uuid for nb in notebooks}


def test_integration_test_endpoint_uses_registry(client, db, user):
    _config(db, user, "notion", config='{"access_token": "t"}')
    _config(db, user, "todoist", config='{"access_token": "t"}')

    resp = client.post(f"{API}/integrations/notion/test")
    assert resp.status_code == 400, resp.text
    assert "database_id" in resp.json()["detail"]

    resp = client.post(f"{API}/integrations/todoist/test")
    assert resp.status_code == 400

    resp = client.post(f"{API}/integrations/unknown/test")
    assert resp.status_code in (400, 404)
