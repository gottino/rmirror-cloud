"""Pages deleted on the tablet: soft removal, undo, Notion cleanup and purge.

Request-level for the ``.content`` upload and the metadata sync (both apply a
page list through ``app/services/page_removal.py``), the views that must hide
removed pages, the sync worker's ``page_removal`` rows (Notion faked) and the
purge of pages removed more than 30 days ago (storage faked).
"""

import io
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from notion_client.errors import APIResponseError
from sqlalchemy import update as sa_update
from sqlalchemy.orm import Session

from app.auth.clerk import get_clerk_active_user, get_clerk_session_user
from app.core.sync_engine import SyncErrorKind
from app.dependencies import get_storage_service
from app.integrations.notion_sync import NotionSyncTarget
from app.models.notebook import Notebook
from app.models.notebook_page import NotebookPage
from app.models.page import OcrStatus, Page
from app.models.sync_record import IntegrationConfig, SyncQueue, SyncRecord, SyncStatus
from app.models.todo import REMOVED_FROM_PAGE, Todo
from app.processors.todo_extractor import process_page_todos
from app.services import page_removal
from app.services.fingerprinting import fingerprint_page
from app.services.page_removal import (
    PAGE_PURGE_AFTER_DAYS,
    apply_page_lists,
    parse_content_pages,
    purge_removed_pages,
)
from app.services.sync_worker import SyncWorker
from tests.conftest import create_user_with_quota
from tests.test_config import test_app  # noqa: F401 - fixture

NB_UUID = "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d"
P1 = "11111111-1111-4111-8111-111111111111"
P2 = "22222222-2222-4222-8222-222222222222"
P3 = "33333333-3333-4333-8333-333333333333"


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def user(db: Session):
    return create_user_with_quota(db, email="pages@example.com", used=0, limit=100)


@pytest.fixture
def notebook(db: Session, user):
    """A notebook with three OCR'd pages P1..P3 (one todo each), mapped 1..3."""
    nb = Notebook(
        user_id=user.id,
        notebook_uuid=NB_UUID,
        visible_name="Journal",
        document_type="notebook",
    )
    db.add(nb)
    db.flush()
    for number, page_uuid in enumerate((P1, P2, P3), start=1):
        page = Page(
            notebook_id=nb.id,
            page_uuid=page_uuid,
            ocr_status=OcrStatus.COMPLETED.value,
            ocr_text=f"findme page {number}\n- [ ] Task {number}",
            s3_key=f"users/{user.id}/notebooks/{NB_UUID}/pages/{page_uuid}.rm",
            pdf_s3_key=f"users/{user.id}/notebooks/{NB_UUID}/pages/{page_uuid}.pdf",
        )
        db.add(page)
        db.flush()
        db.add(NotebookPage(notebook_id=nb.id, page_id=page.id, page_number=number))
    db.commit()
    for page in db.query(Page).filter_by(notebook_id=nb.id):
        process_page_todos(db, page, user.id, force_reprocess=True)
    return nb


@pytest.fixture
def storage():
    storage = MagicMock()
    storage.delete_file = AsyncMock(return_value=True)
    storage.file_exists = AsyncMock(return_value=False)
    storage.download_file = AsyncMock(return_value=b"%PDF")
    return storage


@pytest.fixture
def client(db, test_app, user, storage):  # noqa: F811
    async def _user():
        return user

    test_app.dependency_overrides[get_clerk_active_user] = _user
    test_app.dependency_overrides[get_clerk_session_user] = _user
    test_app.dependency_overrides[get_storage_service] = lambda: storage
    with TestClient(test_app) as c:
        yield c


def _enable(db: Session, user_id: int, target_name: str = "notion") -> IntegrationConfig:
    config = IntegrationConfig(
        user_id=user_id, target_name=target_name, is_enabled=True, config_encrypted="x"
    )
    db.add(config)
    db.commit()
    return config


def _page(db: Session, page_uuid: str) -> Page:
    db.expire_all()
    return db.query(Page).filter_by(page_uuid=page_uuid).one()


def _upload_content(client: TestClient, content: dict):
    return client.post(
        f"/v1/notebooks/{NB_UUID}/content",
        files={
            "content_file": (
                f"{NB_UUID}.content",
                io.BytesIO(json.dumps(content).encode()),
                "application/json",
            )
        },
    )


def _cpages(*entries):
    pages = []
    for page_uuid, deleted in entries:
        entry = {"id": page_uuid, "idx": {"timestamp": "1:2", "value": "ba"}}
        if deleted:
            entry["deleted"] = {"timestamp": "1:3", "value": 1}
        pages.append(entry)
    return {"cPages": {"pages": pages}, "formatVersion": 2}


def _page_list(client: TestClient, notebook_id: int):
    body = client.get(f"/v1/notebooks/{notebook_id}/pages").json()
    return [item["page_uuid"] for item in body["items"]], body["total"]


def _removal_rows(db: Session):
    db.expire_all()
    return db.query(SyncQueue).filter_by(item_type="page_removal").order_by(SyncQueue.id).all()


# --- parsing ----------------------------------------------------------------


def test_parse_content_pages_formats():
    assert parse_content_pages({"pages": [P1, P2.upper()]}) == [P1, P2]
    assert parse_content_pages(_cpages((P1, False), (P2, True), (P3, False))) == [P1, P3]
    # cPages wins when a file has both (it carries the deletion marks)
    both = {**_cpages((P1, False), (P2, True)), "pages": [P1, P2]}
    assert parse_content_pages(both) == [P1]
    assert parse_content_pages({"pages": [P1, "not-a-uuid", P1]}) == [P1]
    assert parse_content_pages({"pages": []}) == []
    assert parse_content_pages({"fileType": "notebook"}) is None
    assert parse_content_pages(["x"]) is None


# --- .content upload --------------------------------------------------------


def test_tombstoned_cpages_entry_hides_page(db, client, notebook):
    resp = _upload_content(client, _cpages((P1, False), (P2, True), (P3, False)))
    assert resp.status_code == 200, resp.text
    assert resp.json()["pages_mapped"] == 2

    assert _page(db, P2).removed_at is not None
    assert _page(db, P1).removed_at is None
    uuids, total = _page_list(client, notebook.id)
    assert uuids == [P1, P3] and total == 2

    body = client.get(f"/v1/notebooks/{notebook.id}").json()
    assert [p["page_uuid"] for p in body["pages"]] == [P1, P3]
    assert body["page_counts"]["total_pages"] == 2
    # The combined notebook PDF is rebuilt without the page.
    db.expire_all()
    assert db.get(Notebook, notebook.id).pdf_dirty_at is not None


def test_absent_page_in_plain_list_is_removed(db, client, notebook):
    assert _upload_content(client, {"pages": [P1, P3]}).status_code == 200
    assert _page(db, P2).removed_at is not None
    assert _page_list(client, notebook.id) == ([P1, P3], 2)


def test_removed_page_todos_are_removed_and_not_queued(db, client, user, notebook):
    _enable(db, user.id, "todoist")
    assert _upload_content(client, {"pages": [P1, P3]}).status_code == 200

    page2 = _page(db, P2)
    todo = db.query(Todo).filter_by(page_id=page2.id).one()
    assert todo.removed_at is not None
    assert todo.removed_reason == REMOVED_FROM_PAGE
    # Other pages' todos are untouched
    assert all(t.removed_at is None for t in db.query(Todo).filter(Todo.page_id != page2.id))
    # Re-extracting other pages never queues the removed page's todo
    from app.services.sync_queue import queue_stored_todos

    queue_stored_todos(db, user.id)
    queued = {row.item_id for row in db.query(SyncQueue).filter_by(item_type="todo")}
    assert str(todo.id) not in queued
    assert queued  # the live todos were queued


def test_undo_restores_page_todos_and_queues_sync(db, client, user, notebook):
    _enable(db, user.id)
    assert _upload_content(client, {"pages": [P1, P3]}).status_code == 200
    page2 = _page(db, P2)
    todo_id = db.query(Todo).filter_by(page_id=page2.id).one().id
    assert len(_removal_rows(db)) == 1

    # Listed again (and in a new position)
    assert _upload_content(client, {"pages": [P2, P1, P3]}).status_code == 200

    page2 = _page(db, P2)
    assert page2.removed_at is None
    assert _page_list(client, notebook.id) == ([P2, P1, P3], 3)
    todo = db.get(Todo, todo_id)
    assert todo.removed_at is None and todo.removed_reason is None
    # The pending removal was cancelled; nothing deletes the toggle now.
    assert _removal_rows(db) == []
    # No sync record for P2 yet, so its page sync was queued (recreates the toggle).
    rows = db.query(SyncQueue).filter_by(item_type="page_text", page_uuid=P2).all()
    assert len(rows) == 1 and rows[0].page_number == 1


def test_empty_list_and_unparseable_content_change_nothing(db, client, notebook):
    assert _upload_content(client, {"pages": []}).status_code == 200
    assert _upload_content(client, {"fileType": "notebook"}).status_code == 200
    assert _upload_content(client, _cpages((P1, True), (P2, True), (P3, True))).status_code == 200
    resp = client.post(
        f"/v1/notebooks/{NB_UUID}/content",
        files={"content_file": (f"{NB_UUID}.content", io.BytesIO(b"{oops"), "application/json")},
    )
    assert resp.status_code == 400
    db.expire_all()
    assert db.query(Page).filter(Page.removed_at.isnot(None)).count() == 0
    assert _page_list(client, notebook.id) == ([P1, P2, P3], 3)


def test_list_removing_all_pages_changes_nothing(db, client, notebook, caplog):
    other = "44444444-4444-4444-8444-444444444444"
    with caplog.at_level("WARNING"):
        assert _upload_content(client, {"pages": [other]}).status_code == 200
    db.expire_all()
    assert db.query(Page).filter(Page.removed_at.isnot(None)).count() == 0
    assert _page_list(client, notebook.id) == ([P1, P2, P3], 3)
    assert any("would remove all" in r.getMessage() for r in caplog.records)


def test_only_pages_of_that_notebook_are_touched(db, user, notebook):
    other_nb = Notebook(
        user_id=user.id, notebook_uuid="other-nb", visible_name="Other", document_type="notebook"
    )
    db.add(other_nb)
    db.flush()
    stray = Page(notebook_id=other_nb.id, page_uuid=P3, ocr_status="completed")
    keep = Page(notebook_id=other_nb.id, page_uuid="55555555-5555-4555-8555-555555555555")
    db.add_all([stray, keep])
    db.commit()

    outcome = apply_page_lists(db, user.id, {notebook.id: [P1, P2]})
    db.commit()
    own_p3 = db.query(Page).filter_by(notebook_id=notebook.id, page_uuid=P3).one()
    assert outcome.removed == {notebook.id: [own_p3.id]}
    db.expire_all()
    assert db.get(Page, stray.id).removed_at is None
    assert db.get(Page, keep.id).removed_at is None

    # Another user's notebook id is never touched
    intruder = create_user_with_quota(db, email="intruder@example.com")
    outcome = apply_page_lists(db, intruder.id, {notebook.id: [P1]})
    assert not outcome.removed
    assert db.query(Page).filter_by(notebook_id=notebook.id, page_uuid=P2).one().removed_at is None


# --- metadata sync (sync.py) ------------------------------------------------


def _metadata(client: TestClient, pages: list[str]):
    resp = client.post(
        "/v1/sync/metadata",
        json={"notebooks": [{"uuid": NB_UUID, "visible_name": "Journal", "pages": pages}]},
    )
    assert resp.status_code == 200, resp.text


def test_metadata_sync_uses_the_same_rule(db, client, user, notebook):
    _enable(db, user.id)
    _metadata(client, [P1, P3])
    assert _page(db, P2).removed_at is not None
    assert db.query(Todo).filter_by(page_id=_page(db, P2).id).one().removed_reason == REMOVED_FROM_PAGE
    assert len(_removal_rows(db)) == 1
    assert _page_list(client, notebook.id) == ([P1, P3], 2)

    # A list that would remove everything is ignored, however often it is
    # sent: the stub the first attempt registers does not count as a kept page.
    for _ in range(3):
        _metadata(client, ["66666666-6666-4666-8666-666666666666"])
        assert _page(db, P1).removed_at is None and _page(db, P3).removed_at is None
        assert _page_list(client, notebook.id) == ([P1, P3], 2)

    # Undo
    _metadata(client, [P1, P2, P3])
    assert _page(db, P2).removed_at is None
    assert _page_list(client, notebook.id) == ([P1, P2, P3], 3)
    assert db.query(Todo).filter_by(page_id=_page(db, P2).id).one().removed_at is None
    # P2's pending removal is cancelled (the stub the refused list created is
    # not listed now, so it is the one removed this time).
    assert [row.page_uuid for row in _removal_rows(db)] == ["66666666-6666-4666-8666-666666666666"]


# --- views ------------------------------------------------------------------


def test_removed_pages_hidden_from_search_export_obsidian_stats(db, client, user, notebook):
    from app.services.obsidian_service import generate_api_key, hash_api_key
    from app.services.search_service import search

    assert _upload_content(client, {"pages": [P1, P3]}).status_code == 200

    # Search
    result = search(db, user.id, "findme")
    texts = json.dumps(result.model_dump(), default=str)
    assert "page 1" in texts and "page 2" not in texts

    # Markdown export
    resp = client.get(f"/v1/notebooks/{notebook.id}/export", params={"format": "markdown"})
    assert resp.status_code == 200, resp.text
    assert "findme page 1" in resp.text and "findme page 2" not in resp.text

    # Combined PDF / PDF export page keys
    from app.services.notebook_pdf import _page_pdf_keys

    keys = _page_pdf_keys(db, notebook.id)
    assert len(keys) == 2 and not any(P2 in key for key in keys)

    # Page PDF endpoint: 404 for a removed page
    assert client.get(f"/v1/pages/{_page(db, P2).id}/pdf").status_code == 404

    # Obsidian pull
    api_key = generate_api_key()
    db.add(
        IntegrationConfig(
            user_id=user.id,
            target_name="obsidian",
            is_enabled=True,
            config_encrypted="x",
            api_key_hash=hash_api_key(api_key),
        )
    )
    db.commit()
    body = client.get(
        "/v1/integrations/obsidian/sync", headers={"Authorization": f"Bearer {api_key}"}
    ).json()
    page_uuids = [p["page_uuid"] for nb in body["notebooks"] for p in nb["pages"]]
    assert sorted(page_uuids) == sorted([P1, P3])

    # Dashboard notebook list counts
    tree = client.get("/v1/notebooks/tree").json()
    assert P2 not in json.dumps(tree)
    assert "findme page 2" not in json.dumps(tree)


def test_onboarding_counts_ignore_removed_pages(db, client, user, notebook):
    # Only P1 is OCR'd; once it is removed there is no OCR'd page left to count.
    db.query(Page).filter(Page.page_uuid != P1).update({Page.ocr_status: "not_synced"})
    db.commit()
    assert client.get("/v1/onboarding/progress").json()["has_ocr"] is True
    apply_page_lists(db, user.id, {notebook.id: [P2, P3]})
    db.commit()
    assert client.get("/v1/onboarding/progress").json()["has_ocr"] is False


# --- Notion removal (queue + worker) ----------------------------------------


def test_no_removal_queued_without_enabled_notion(db, client, user, notebook):
    _enable(db, user.id, "todoist")
    config = _enable(db, user.id, "notion")
    config.is_enabled = False
    db.commit()
    assert _upload_content(client, {"pages": [P1, P3]}).status_code == 200
    assert _removal_rows(db) == []


def _record(db, user, page_uuid, block_id, item_type="page_text", **extra):
    record = SyncRecord(
        user_id=user.id,
        target_name="notion",
        item_type=item_type,
        item_id="1",
        content_hash=extra.pop("content_hash", "h"),
        external_id=block_id,
        status="success",
        page_uuid=page_uuid,
        notebook_uuid=NB_UUID,
        **extra,
    )
    db.add(record)
    db.commit()
    return record


def _notion_error(status: int, code: str, message: str) -> APIResponseError:
    response = MagicMock()
    response.status_code = status
    response.headers = {}
    response.text = json.dumps({"code": code, "message": message})
    try:
        return APIResponseError(response, message, code)
    except TypeError:  # older/newer constructor signature
        return APIResponseError(code=code, status=status, message=message, headers={}, raw_body_text="")


def _toggle(parent_page_id: str = "nbpage-1") -> dict:
    """What Notion returns for a page toggle on the notebook page."""
    return {"type": "toggle", "parent": {"type": "page_id", "page_id": parent_page_id}}


def _notion() -> MagicMock:
    notion = MagicMock()
    notion.blocks.retrieve.return_value = _toggle()
    return notion


async def _run_removal(db, user, notion_client):
    config = db.query(IntegrationConfig).filter_by(user_id=user.id, target_name="notion").one()
    row = _removal_rows(db)[0]
    with patch("app.integrations.notion_sync.NotionClient", return_value=notion_client), patch.object(
        IntegrationConfig, "get_config", return_value={"access_token": "t", "database_id": "d"}
    ):
        await SyncWorker()._process_page_removal(db, row, config)
    db.expire_all()
    return db.get(SyncQueue, row.id)


@pytest.mark.asyncio
async def test_worker_archives_block_and_forgets_record(db, client, user, notebook):
    _enable(db, user.id)
    _record(db, user, None, "nbpage-1", item_type="notebook")
    _record(db, user, P2, "block-2")
    _record(db, user, P1, "block-1")
    assert _upload_content(client, {"pages": [P1, P3]}).status_code == 200
    notion = _notion()

    row = await _run_removal(db, user, notion)

    assert row.status == "completed"
    notion.blocks.delete.assert_called_once_with(block_id="block-2")
    assert db.query(SyncRecord).filter_by(page_uuid=P2).count() == 0
    assert db.query(SyncRecord).filter_by(page_uuid=P1).count() == 1

    # Undo afterwards queues a fresh page sync (no record left, toggle recreated)
    assert _upload_content(client, {"pages": [P1, P2, P3]}).status_code == 200
    assert db.query(SyncQueue).filter_by(item_type="page_text", page_uuid=P2).count() == 1


@pytest.mark.asyncio
async def test_worker_treats_not_found_as_removed(db, client, user, notebook):
    _enable(db, user.id)
    _record(db, user, None, "nbpage-1", item_type="notebook")
    _record(db, user, P2, "block-2")
    assert _upload_content(client, {"pages": [P1, P3]}).status_code == 200
    notion = _notion()
    notion.blocks.delete.side_effect = _notion_error(404, "object_not_found", "Could not find block")

    row = await _run_removal(db, user, notion)

    assert row.status == "completed"
    assert db.query(SyncRecord).filter_by(page_uuid=P2).count() == 0


@pytest.mark.asyncio
async def test_worker_retries_transient_failure_and_keeps_record(db, client, user, notebook):
    _enable(db, user.id)
    _record(db, user, None, "nbpage-1", item_type="notebook")
    _record(db, user, P2, "block-2")
    assert _upload_content(client, {"pages": [P1, P3]}).status_code == 200
    notion = _notion()
    notion.blocks.delete.side_effect = _notion_error(502, "service_unavailable", "down")

    row = await _run_removal(db, user, notion)

    assert row.status == "pending" and row.retry_count == 1
    assert db.query(SyncRecord).filter_by(page_uuid=P2).count() == 1


@pytest.mark.asyncio
async def test_worker_skips_page_restored_before_it_ran(db, client, user, notebook):
    _enable(db, user.id)
    _record(db, user, P2, "block-2")
    assert _upload_content(client, {"pages": [P1, P3]}).status_code == 200
    row = _removal_rows(db)[0]
    # Restored behind the worker's back (row already claimed)
    row.status = "processing"
    _page(db, P2).removed_at = None
    db.commit()
    notion = MagicMock()
    config = db.query(IntegrationConfig).filter_by(user_id=user.id, target_name="notion").one()
    with patch("app.integrations.notion_sync.NotionClient", return_value=notion):
        await SyncWorker()._process_page_removal(db, row, config)
    assert row.status == "completed"
    notion.blocks.delete.assert_not_called()
    assert db.query(SyncRecord).filter_by(page_uuid=P2).count() == 1


@pytest.mark.asyncio
async def test_page_sync_of_removed_page_is_skipped(db, user, notebook):
    config = _enable(db, user.id)
    page = db.query(Page).filter_by(page_uuid=P2).one()
    row = SyncQueue(
        user_id=user.id,
        item_type="page_text",
        item_id=str(page.id),
        content_hash="h",
        page_uuid=P2,
        notebook_uuid=NB_UUID,
        page_number=2,
        target_name="notion",
        status="processing",
    )
    db.add(row)
    apply_page_lists(db, user.id, {notebook.id: [P1, P3]})
    db.commit()
    target = MagicMock()
    target.sync_item = AsyncMock()
    with patch("app.services.sync_worker.create_target", return_value=target), patch.object(
        IntegrationConfig, "get_config", return_value={}
    ):
        await SyncWorker()._process_page_sync(db, row, config)
    assert row.status == "completed"
    target.sync_item.assert_not_called()


@pytest.mark.asyncio
async def test_remove_page_block_classifies_errors():
    with patch("app.integrations.notion_sync.NotionClient") as client_cls:
        target = NotionSyncTarget(access_token="t", database_id="d")
        notion = client_cls.return_value

        notion.blocks.retrieve.return_value = _toggle()

        notion.blocks.delete.side_effect = _notion_error(400, "validation_error", "Can't edit block that is archived")
        assert (await target.remove_page_block("b", "nbpage-1")).success

        notion.blocks.delete.side_effect = _notion_error(429, "rate_limited", "slow down")
        result = await target.remove_page_block("b", "nbpage-1")
        assert not result.success and result.error_kind is SyncErrorKind.RATE_LIMITED

        notion.blocks.delete.side_effect = None
        result = await target.remove_page_block("b", "nbpage-1")
        assert result.status == SyncStatus.SUCCESS

        # A block that has gone missing counts as removed
        notion.blocks.retrieve.side_effect = _notion_error(404, "object_not_found", "Could not find block")
        assert (await target.remove_page_block("b", "nbpage-1")).success


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "block",
    [
        {"type": "child_page", "parent": {"type": "page_id", "page_id": "nbpage-1"}},  # not a toggle
        {"type": "toggle", "parent": {"type": "page_id", "page_id": "other-page"}},  # another page
        {"type": "toggle", "parent": {"type": "block_id", "block_id": "x"}},  # nested
        {"object": "page", "parent": {"type": "database_id", "database_id": "d"}},  # a page
    ],
)
async def test_remove_page_block_only_deletes_toggles_on_the_notebook_page(block):
    with patch("app.integrations.notion_sync.NotionClient") as client_cls:
        target = NotionSyncTarget(access_token="t", database_id="d")
        notion = client_cls.return_value
        notion.blocks.retrieve.return_value = block

        result = await target.remove_page_block("b", "nbpage-1")

        assert result.success and result.metadata["action"] == "not_a_page_toggle"
        notion.blocks.delete.assert_not_called()


@pytest.mark.asyncio
async def test_worker_deletes_nothing_without_a_notebook_record(db, client, user, notebook):
    _enable(db, user.id)
    _record(db, user, P2, "block-2")  # no notebook record: the id cannot be checked
    assert _upload_content(client, {"pages": [P1, P3]}).status_code == 200
    notion = _notion()

    row = await _run_removal(db, user, notion)

    assert row.status == "completed"
    notion.blocks.retrieve.assert_not_called()
    notion.blocks.delete.assert_not_called()
    assert db.query(SyncRecord).filter_by(page_uuid=P2).count() == 0


@pytest.mark.asyncio
async def test_page_restored_during_its_removal_is_synced_again(db, client, user, notebook):
    _enable(db, user.id)
    _record(db, user, None, "nbpage-1", item_type="notebook")
    # In sync: the record has the page's current fingerprint.
    in_sync = fingerprint_page(NB_UUID, 2, _page(db, P2).ocr_text, P2)
    _record(db, user, P2, "block-2", content_hash=in_sync)
    assert _upload_content(client, {"pages": [P1, P3]}).status_code == 200
    row = _removal_rows(db)[0]
    row.status = "processing"  # claimed by the worker
    db.commit()
    notion = _notion()

    def restore_meanwhile(**_kwargs):
        # The undo arrives while Notion is being called: the removal row is
        # not pending, and the record still there means nothing is queued.
        assert _upload_content(client, {"pages": [P1, P2, P3]}).status_code == 200
        assert db.query(SyncQueue).filter_by(item_type="page_text", page_uuid=P2).count() == 0

    notion.blocks.delete.side_effect = restore_meanwhile
    config = db.query(IntegrationConfig).filter_by(user_id=user.id, target_name="notion").one()
    with patch("app.integrations.notion_sync.NotionClient", return_value=notion), patch.object(
        IntegrationConfig, "get_config", return_value={"access_token": "t", "database_id": "d"}
    ):
        await SyncWorker()._process_page_removal(db, row, config)

    db.expire_all()
    assert _page(db, P2).removed_at is None
    assert db.query(SyncRecord).filter_by(page_uuid=P2, item_type="page_text").count() == 0
    # The toggle was deleted, so the page is queued to get a new one.
    assert db.query(SyncQueue).filter_by(item_type="page_text", page_uuid=P2, status="pending").count() == 1


# --- purge ------------------------------------------------------------------


def _age(db, page_uuid, days):
    page = _page(db, page_uuid)
    page.removed_at = datetime.utcnow() - timedelta(days=days)
    db.commit()
    return page.id


@pytest.mark.asyncio
async def test_purge_deletes_only_after_30_days(db, user, notebook, storage):
    apply_page_lists(db, user.id, {notebook.id: [P1]})
    db.commit()
    old_id = _age(db, P2, PAGE_PURGE_AFTER_DAYS + 1)
    young_id = _age(db, P3, PAGE_PURGE_AFTER_DAYS - 1)
    _record(db, user, P2, "block-2")
    todo_id = db.query(Todo).filter_by(page_id=old_id).one().id
    db.add(SyncRecord(user_id=user.id, target_name="todoist", item_type="todo", item_id=str(todo_id),
                      content_hash="t", external_id="task", status="success"))
    db.commit()

    assert await purge_removed_pages(db, storage) == 1

    db.expire_all()
    assert db.get(Page, old_id) is None
    assert db.get(Page, young_id) is not None
    assert db.query(Todo).filter_by(id=todo_id).count() == 0
    assert db.query(SyncRecord).filter_by(page_uuid=P2).count() == 0
    assert db.query(SyncRecord).filter_by(item_type="todo", item_id=str(todo_id)).count() == 0
    deleted = [call.args[0] for call in storage.delete_file.await_args_list]
    assert sorted(deleted) == sorted(
        [f"users/{user.id}/notebooks/{NB_UUID}/pages/{P2}.rm",
         f"users/{user.id}/notebooks/{NB_UUID}/pages/{P2}.pdf"]
    )
    # Live page untouched
    assert _page(db, P1).removed_at is None


@pytest.mark.asyncio
async def test_purge_leaves_a_page_restored_after_it_was_selected(db, client, user, notebook, storage):
    assert _upload_content(client, {"pages": [P1, P3]}).status_code == 200
    _age(db, P2, PAGE_PURGE_AFTER_DAYS + 1)
    page_id = _page(db, P2).id

    original = db.execute
    calls = {"n": 0}

    def execute(statement, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:  # after the candidate query, before the row is locked
            original(sa_update(Page).where(Page.id == page_id).values(removed_at=None))
            db.commit()
        return original(statement, *args, **kwargs)

    with patch.object(db, "execute", side_effect=execute):
        assert await purge_removed_pages(db, storage) == 0

    storage.delete_file.assert_not_called()  # its files are untouched
    db.expire_all()
    assert _page(db, P2).removed_at is None


@pytest.mark.asyncio
async def test_purge_retries_when_storage_delete_fails(db, user, notebook, storage):
    apply_page_lists(db, user.id, {notebook.id: [P1, P3]})
    db.commit()
    page_id = _age(db, P2, PAGE_PURGE_AFTER_DAYS + 5)

    storage.delete_file = AsyncMock(side_effect=RuntimeError("s3 down"))
    assert await purge_removed_pages(db, storage) == 0
    db.expire_all()
    assert db.get(Page, page_id) is not None

    # delete_file returns False and the file is still there: also kept
    storage.delete_file = AsyncMock(return_value=False)
    storage.file_exists = AsyncMock(return_value=True)
    assert await purge_removed_pages(db, storage) == 0
    assert db.get(Page, page_id) is not None

    storage.delete_file = AsyncMock(return_value=True)
    assert await purge_removed_pages(db, storage) == 1
    db.expire_all()
    assert db.get(Page, page_id) is None


@pytest.mark.asyncio
async def test_worker_purge_is_throttled(db, storage):
    worker = SyncWorker()
    calls = []

    async def fake_purge(session, store):
        calls.append(store)
        return 0

    with patch("app.services.sync_worker.SessionLocal", return_value=db), patch.object(
        page_removal, "purge_removed_pages", fake_purge
    ), patch("app.dependencies.get_storage_service", return_value=storage), patch.object(
        db, "close"
    ):
        await worker._purge_removed_pages()
        await worker._purge_removed_pages()
    assert len(calls) == 1



# --- review follow-ups ------------------------------------------------------


@pytest.mark.asyncio
async def test_account_export_includes_removed_pages_still_stored(db, client, user, notebook, storage):
    import io
    import zipfile

    from app.services.account_service import AccountService

    assert _upload_content(client, {"pages": [P1, P3]}).status_code == 200
    buffer = io.BytesIO()
    await AccountService.write_data_export(user.id, db, storage, buffer)

    with zipfile.ZipFile(buffer) as zf:
        names = zf.namelist()
        metadata = json.loads(zf.read("rmirror-export/metadata.json"))
        [deleted_md] = [n for n in names if n.endswith(" - deleted pages.md")]
        deleted_text = zf.read(deleted_md).decode()
        [live_md] = [n for n in names if n.endswith(".md") and n != deleted_md]
        live_text = zf.read(live_md).decode()

    assert metadata["total_pages"] == 2
    assert metadata["deleted_pages_awaiting_removal"] == 1
    assert metadata["notebooks"][0]["deleted_pages_awaiting_removal"] == 1
    assert "findme page 2" in deleted_text and "findme page 2" not in live_text
    assert "findme page 1" in live_text and "findme page 1" not in deleted_text


def test_pending_removal_row_is_not_taken_for_the_pages_text_sync(db, client, user, notebook):
    from app.services.sync_queue import queue_sync

    _enable(db, user.id)
    assert _upload_content(client, {"pages": [P1, P3]}).status_code == 200
    [removal] = _removal_rows(db)
    page = _page(db, P2)

    queued = queue_sync(
        db=db,
        user_id=user.id,
        item_type="page_text",
        item_id=str(page.id),
        content_hash="new-text-hash",
        target_name="notion",
        page_uuid=P2,
        notebook_uuid=NB_UUID,
        page_number=2,
    )

    db.expire_all()
    assert queued is not None and queued.id != removal.id and queued.item_type == "page_text"
    assert db.get(SyncQueue, removal.id).content_hash != "new-text-hash"
