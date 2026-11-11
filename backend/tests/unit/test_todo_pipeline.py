"""Todos end to end: upload -> extraction -> queue -> worker -> target.

Request-level: POST /v1/processing/rm-file with the converter and OCR faked
(OCR returns the text under test), the todos API, and the sync worker run on
the same SQLite session with the todo target faked through the registry.

- Every page OCR'd with text has its todos stored; queue rows only for enabled
  todo targets.
- Re-extraction is idempotent; a changed text updates and re-queues the todo; a
  checked box arrives completed; a line gone from the page marks the todo
  removed (nothing deleted remotely).
- Extraction failing never fails the upload.
- Backfill (POST /todos/extract) and connecting a target queue stored todos once.
"""

import io
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.clerk import get_clerk_active_user
from app.core.sync_engine import SyncResult
from app.dependencies import get_storage_service
from app.models.page import OcrStatus, Page
from app.models.sync_record import IntegrationConfig, SyncQueue, SyncRecord, SyncStatus
from app.models.todo import REMOVED_BY_USER, REMOVED_FROM_PAGE, Todo
from app.services.sync_worker import SyncWorker
from tests.conftest import create_user_with_quota
from tests.test_config import test_app  # noqa: F401 - fixture

PAGE_UUID = "5d0c6e2a-8b1f-4c3d-9e7a-2f4b6c8d0e1a"
NB_UUID = "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d"


@pytest.fixture
def api(db, test_app, reset_rate_limiter):  # noqa: F811
    """Returns (upload(text), client, user); each upload sends new file bytes."""
    user = create_user_with_quota(db, email="todos@example.com", used=0, limit=100)
    storage = MagicMock()
    storage.upload_file = AsyncMock()
    test_app.dependency_overrides[get_storage_service] = lambda: storage

    async def _user():
        return user

    test_app.dependency_overrides[get_clerk_active_user] = _user

    converter = MagicMock()
    converter.has_content.return_value = True
    converter.rm_to_pdf_bytes.return_value = b"%PDF fake"
    ocr = MagicMock()
    ocr.extract_text_from_pdf = AsyncMock()
    counter = {"n": 0}

    with patch("app.api.processing.RMConverter", return_value=converter), patch(
        "app.api.processing.OCRService", return_value=ocr
    ), patch("app.services.quota_service.get_email_service"), TestClient(test_app) as client:

        def upload(text):
            counter["n"] += 1  # new bytes: the page is re-OCR'd
            ocr.extract_text_from_pdf.return_value = text
            resp = client.post(
                "/v1/processing/rm-file",
                files={
                    "rm_file": (
                        f"{PAGE_UUID}.rm",
                        io.BytesIO(f"page-v{counter['n']}".encode()),
                        "application/octet-stream",
                    ),
                    "metadata_file": (
                        f"{NB_UUID}.metadata",
                        io.BytesIO(b'{"visibleName": "Errands", "type": "DocumentType"}'),
                        "application/json",
                    ),
                },
            )
            assert resp.status_code == 200, resp.text
            return resp

        yield upload, client, user
    test_app.dependency_overrides.pop(get_storage_service, None)
    test_app.dependency_overrides.pop(get_clerk_active_user, None)


def _enable(db: Session, user_id: int, target_name: str) -> None:
    db.add(
        IntegrationConfig(
            user_id=user_id, target_name=target_name, is_enabled=True, config_encrypted="x"
        )
    )
    db.commit()


def _todos(db: Session, **filters) -> list[Todo]:
    db.expire_all()
    return db.query(Todo).filter_by(**filters).order_by(Todo.id).all()


def _todo_rows(db: Session, **filters) -> list[SyncQueue]:
    db.expire_all()
    return db.query(SyncQueue).filter_by(item_type="todo", **filters).order_by(SyncQueue.id).all()


class FakeTodoist:
    """Stands in for TodoistSyncTarget (patched in the target registry)."""

    def __init__(self):
        self.created: list[dict] = []
        self.updated: list[tuple[str, dict]] = []

    def __call__(self, **_config):
        return self

    async def sync_item(self, item):
        self.created.append(dict(item.data))
        return SyncResult(status=SyncStatus.SUCCESS, target_id=f"task_{len(self.created)}")

    async def update_item(self, external_id, item):
        self.updated.append((external_id, dict(item.data)))
        return SyncResult(status=SyncStatus.SUCCESS, target_id=external_id)

    async def delete_item(self, external_id):  # must never be called
        raise AssertionError("remote delete must not happen")


class _Unclosable:
    """The test session, handed to code that closes its own session when done."""

    def __init__(self, db: Session):
        self._db = db

    def close(self):
        pass

    def __getattr__(self, name):
        return getattr(self._db, name)


async def _run_worker(db: Session, fake: FakeTodoist) -> None:
    with patch("app.services.sync_worker.SessionLocal", return_value=_Unclosable(db)), patch(
        "app.integrations.registry.TodoistSyncTarget", fake
    ), patch.object(IntegrationConfig, "get_config", return_value={"access_token": "t"}):
        await SyncWorker()._process_pending_items()


# ---------------------------------------------------------------------------
# Upload -> todo -> Todoist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_checkbox_on_uploaded_page_reaches_todoist_once(db, api):
    upload, _, user = api
    _enable(db, user.id, "todoist")
    _enable(db, user.id, "notion")

    upload("Meeting notes\n- [ ] Buy milk\nnot a task")

    [todo] = _todos(db)
    assert todo.text == "Buy milk" and todo.completed is False
    [row] = _todo_rows(db)
    assert row.target_name == "todoist" and row.item_id == str(todo.id)
    # The notebook target gets the page, never the todo.
    assert db.query(SyncQueue).filter_by(target_name="notion", item_type="todo").count() == 0

    fake = FakeTodoist()
    await _run_worker(db, fake)
    await _run_worker(db, fake)
    assert [c["text"] for c in fake.created] == ["Buy milk"]
    assert fake.updated == []
    record = db.query(SyncRecord).filter_by(item_type="todo", target_name="todoist").one()
    assert record.item_id == str(todo.id) and record.external_id == "task_1"


@pytest.mark.asyncio
async def test_reupload_with_same_todos_creates_nothing(db, api):
    upload, _, user = api
    _enable(db, user.id, "todoist")
    upload("- [ ] Buy milk\n- [ ] Call Bob")
    fake = FakeTodoist()
    await _run_worker(db, fake)

    upload("- [ ] Buy milk\n- [ ] Call Bob\nsome new notes")
    await _run_worker(db, fake)

    assert len(_todos(db)) == 2
    assert len(_todo_rows(db)) == 2  # the two first syncs, nothing new
    assert len(fake.created) == 2 and fake.updated == []


@pytest.mark.asyncio
async def test_changed_todo_text_updates_the_same_task(db, api):
    upload, _, user = api
    _enable(db, user.id, "todoist")
    upload("- [ ] Book the dentist appointmnt")
    fake = FakeTodoist()
    await _run_worker(db, fake)
    [todo] = _todos(db)

    upload("- [ ] Book the dentist appointment")
    await _run_worker(db, fake)

    [same] = _todos(db)
    assert same.id == todo.id and same.text == "Book the dentist appointment"
    assert len(fake.created) == 1
    assert [(ext, data["text"]) for ext, data in fake.updated] == [
        ("task_1", "Book the dentist appointment")
    ]


@pytest.mark.asyncio
async def test_checked_box_arrives_completed(db, api):
    upload, _, user = api
    _enable(db, user.id, "todoist")
    upload("- [ ] Buy milk\n- [x] Pay rent")
    fake = FakeTodoist()
    await _run_worker(db, fake)
    # First sync: a box already checked is created completed.
    assert {c["text"]: c["completed"] for c in fake.created} == {
        "Buy milk": False,
        "Pay rent": True,
    }

    # Later the other box is checked too: the existing task is completed.
    upload("- [x] Buy milk\n- [x] Pay rent")
    await _run_worker(db, fake)
    assert len(fake.created) == 2
    [(external_id, data)] = fake.updated
    assert data["text"] == "Buy milk" and data["completed"] is True
    assert data["previous_completed"] is False
    assert all(t.completed for t in _todos(db))


@pytest.mark.asyncio
async def test_todo_gone_from_page_is_marked_removed_not_deleted(db, api):
    upload, client, user = api
    _enable(db, user.id, "todoist")
    upload("- [ ] Buy milk\n- [ ] Call Bob")
    fake = FakeTodoist()
    await _run_worker(db, fake)

    upload("- [ ] Buy milk")
    await _run_worker(db, fake)  # FakeTodoist.delete_item would raise

    gone = _todos(db, text="Call Bob")[0]
    assert gone.removed_at is not None and gone.removed_reason == REMOVED_FROM_PAGE
    assert [t["text"] for t in client.get("/v1/todos/").json()] == ["Buy milk"]
    assert fake.updated == []

    # The line comes back: same todo, live again, no second task.
    upload("- [ ] Buy milk\n- [ ] Call Bob")
    await _run_worker(db, fake)
    back = _todos(db, text="Call Bob")
    assert [t.id for t in back] == [gone.id] and back[0].removed_at is None
    assert len(fake.created) == 2


# ---------------------------------------------------------------------------
# No todo target / failures
# ---------------------------------------------------------------------------


def test_without_todo_target_todos_are_stored_but_not_queued(db, api):
    upload, _, user = api
    _enable(db, user.id, "notion")  # a notebook target only

    upload("- [ ] Buy milk")

    assert [t.text for t in _todos(db)] == ["Buy milk"]
    assert _todo_rows(db) == []
    assert db.query(SyncQueue).filter_by(item_type="page_text").count() == 1


def test_extraction_failure_does_not_fail_the_upload(db, api):
    upload, client, user = api
    _enable(db, user.id, "notion")

    with patch(
        "app.processors.todo_extractor.process_page_todos", side_effect=RuntimeError("boom")
    ):
        resp = upload("- [ ] Buy milk")

    assert resp.json()["success"] is True
    db.expire_all()
    page = db.query(Page).filter_by(page_uuid=PAGE_UUID).one()
    assert page.ocr_status == OcrStatus.COMPLETED
    assert db.query(SyncQueue).filter_by(item_type="page_text").count() == 1
    assert _todos(db) == []
    # The session is still usable for the rest of the request and afterwards.
    assert client.get("/v1/todos/").status_code == 200


def test_extraction_error_inside_the_session_is_rolled_back(db, api):
    """A failing flush (not just a raised exception) leaves the session usable."""
    upload, client, user = api
    _enable(db, user.id, "todoist")

    with patch(
        "app.processors.todo_extractor.enabled_todo_targets",
        side_effect=RuntimeError("db hiccup"),
    ):
        upload("- [ ] Buy milk")
    # Stored even though queueing failed; queueing catches up on the next upload.
    assert [t.text for t in _todos(db)] == ["Buy milk"]
    assert _todo_rows(db) == []
    upload("- [ ] Buy milk\nmore")
    assert len(_todo_rows(db)) == 1


# ---------------------------------------------------------------------------
# Backfill, connecting a target, PATCH and DELETE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backfill_queues_stored_todos_once_after_target_is_enabled(db, api):
    upload, client, user = api
    upload("- [ ] Buy milk\n- [x] Pay rent")
    assert _todo_rows(db) == []

    _enable(db, user.id, "todoist")
    with patch("app.api.todos.SessionLocal", return_value=_Unclosable(db)):
        assert client.post("/v1/todos/extract", json={}).status_code == 200
        assert len(_todo_rows(db)) == 2
        assert client.post("/v1/todos/extract", json={}).status_code == 200
        assert len(_todo_rows(db)) == 2  # pending rows reused

        fake = FakeTodoist()
        await _run_worker(db, fake)
        assert client.post("/v1/todos/extract", json={"force_reprocess": True}).status_code == 200
    assert len(_todo_rows(db)) == 2  # synced: nothing new
    assert sorted(c["text"] for c in fake.created) == ["Buy milk", "Pay rent"]
    assert len(_todos(db)) == 2


def test_backfill_extracts_pages_ocrd_before(db, api):
    """Pages OCR'd before automatic extraction get their todos from the backfill."""
    upload, client, user = api
    with patch("app.services.page_events.extract_todos_after_ocr"):
        upload("- [ ] Old task")
    assert _todos(db) == []

    with patch("app.api.todos.SessionLocal", return_value=_Unclosable(db)):
        assert client.post("/v1/todos/extract", json={}).status_code == 200
    assert [t.text for t in _todos(db)] == ["Old task"]


@pytest.mark.asyncio
async def test_connecting_notion_todos_queues_stored_todos(db, api):
    from app.services.initial_sync import trigger_initial_sync

    upload, _, user = api
    upload("- [ ] Buy milk")
    _enable(db, user.id, "notion-todos")

    result = await trigger_initial_sync(db, user.id, "notion-todos")

    assert result["queued_count"] == 1
    rows = db.query(SyncQueue).filter_by(target_name="notion-todos").all()
    assert [r.item_type for r in rows] == ["todo"]  # no page_text rows for a todo target


@pytest.mark.asyncio
async def test_patch_queues_the_change(db, api):
    upload, client, user = api
    _enable(db, user.id, "todoist")
    upload("- [ ] Buy milk")
    fake = FakeTodoist()
    await _run_worker(db, fake)
    [todo] = _todos(db)

    resp = client.patch(f"/v1/todos/{todo.id}", json={"completed": True})
    assert resp.status_code == 200 and resp.json()["completed"] is True
    await _run_worker(db, fake)

    [(external_id, data)] = fake.updated
    assert external_id == "task_1" and data["completed"] is True


@pytest.mark.asyncio
async def test_delete_marks_removed_and_is_not_extracted_again(db, api):
    upload, client, user = api
    _enable(db, user.id, "todoist")
    upload("- [ ] Buy milk")
    fake = FakeTodoist()
    await _run_worker(db, fake)
    [todo] = _todos(db)

    assert client.delete(f"/v1/todos/{todo.id}").status_code == 204
    assert client.get(f"/v1/todos/{todo.id}").status_code == 404
    assert client.get("/v1/todos/").json() == []

    upload("- [ ] Buy milk\nmore notes")  # line still on the page
    await _run_worker(db, fake)  # FakeTodoist.delete_item would raise
    [still] = _todos(db)
    assert still.removed_reason == REMOVED_BY_USER and still.removed_at <= datetime.utcnow()
    assert len(fake.created) == 1 and fake.updated == []
