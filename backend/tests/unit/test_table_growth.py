"""Bounded growth of the sync tables.

- Finished sync_queue rows are pruned after their retention period.
- queue_sync writes no row when an item is already in sync.
- /processing/metadata/update only enqueues a coalesced notebook_metadata item;
  the worker syncs it and keeps one sync record per notebook and target.
- /health counts are bounded.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

import app.main as main_module
from app.api.processing import UpdateMetadataRequest, update_notebook_metadata
from app.core.sync_engine import SyncResult
from app.models.notebook import Notebook
from app.models.sync_record import IntegrationConfig, SyncQueue, SyncRecord, SyncStatus
from app.services.sync_queue import prune_sync_queue, queue_notebook_metadata_sync, queue_sync
from app.services.sync_worker import SyncWorker
from tests.conftest import create_user_with_quota

NOW = datetime(2026, 11, 1, 12, 0, 0)
NB_UUID = "0b0b0b0b-0000-4000-8000-000000000001"
NOTION_CONFIG = {"access_token": "test-token", "database_id": "db-123"}


@pytest.fixture
def user(db: Session):
    return create_user_with_quota(db, used=0, limit=30)


@pytest.fixture
def notion_config(db: Session, user):
    config = IntegrationConfig(
        user_id=user.id,
        target_name="notion",
        is_enabled=True,
        config_encrypted="unused",
    )
    db.add(config)
    db.commit()
    return config


@pytest.fixture
def notebook(db: Session, user):
    nb = Notebook(
        notebook_uuid=NB_UUID,
        user_id=user.id,
        visible_name="Growth",
        document_type="notebook",
    )
    db.add(nb)
    db.commit()
    db.refresh(nb)
    return nb


def _queue_row(db, user, status, age_days, completed_at_age=None, item_type="page_text"):
    ts = NOW - timedelta(days=age_days)
    row = SyncQueue(
        user_id=user.id,
        item_type=item_type,
        item_id="1",
        content_hash=f"h-{status}-{age_days}",
        target_name="notion",
        status=status,
        created_at=ts,
        updated_at=ts,
        completed_at=(
            NOW - timedelta(days=completed_at_age) if completed_at_age is not None else None
        ),
    )
    db.add(row)
    db.commit()
    return row.id


# ------------------------------------------------------------------ prune


def test_prune_deletes_only_old_finished_rows(db, user):
    old_completed = _queue_row(db, user, "completed", 40, completed_at_age=40)
    old_completed_no_ts = _queue_row(db, user, "completed", 40)  # falls back to updated_at
    recent_completed = _queue_row(db, user, "completed", 40, completed_at_age=5)
    old_failed = _queue_row(db, user, "failed", 100)
    recent_failed = _queue_row(db, user, "failed", 40)
    old_pending = _queue_row(db, user, "pending", 400)
    old_processing = _queue_row(db, user, "processing", 400)

    deleted = prune_sync_queue(db, completed_days=30, failed_days=90, now=NOW)

    remaining = {r.id for r in db.query(SyncQueue.id)}
    assert deleted == 3
    assert remaining == {recent_completed, recent_failed, old_pending, old_processing}
    assert old_completed not in remaining and old_completed_no_ts not in remaining
    assert old_failed not in remaining


def test_prune_works_in_bounded_batches(db, user):
    for _ in range(5):
        _queue_row(db, user, "completed", 60, completed_at_age=60)

    first = prune_sync_queue(
        db, completed_days=30, failed_days=90, now=NOW, batch_size=2, max_batches=1
    )
    assert first == 2
    assert db.query(SyncQueue).count() == 3

    rest = prune_sync_queue(db, completed_days=30, failed_days=90, now=NOW, batch_size=2)
    assert rest == 3
    assert db.query(SyncQueue).count() == 0


def test_prune_disabled_with_zero_retention(db, user):
    _queue_row(db, user, "completed", 400, completed_at_age=400)
    _queue_row(db, user, "failed", 400)

    assert prune_sync_queue(db, completed_days=0, failed_days=0, now=NOW) == 0
    assert db.query(SyncQueue).count() == 2


def test_worker_prunes_about_hourly(db, user):
    worker = SyncWorker()
    with patch("app.services.sync_worker.SessionLocal", return_value=db), \
         patch.object(db, "close"), \
         patch("app.services.sync_queue.prune_sync_queue", return_value=0) as prune:
        worker._prune_sync_queue()
        worker._prune_sync_queue()
        assert prune.call_count == 1
        kwargs = prune.call_args.kwargs
        assert kwargs["completed_days"] >= 30
        assert kwargs["failed_days"] >= 30

        worker._last_queue_prune -= 3601
        worker._prune_sync_queue()
        assert prune.call_count == 2


# ------------------------------------------------------------------ queue_sync


def test_queue_sync_writes_no_row_for_synced_non_page_item(db, user):
    db.add(
        SyncRecord(
            user_id=user.id,
            target_name="notion-todos",
            item_type="todo",
            item_id="7",
            content_hash="todo-hash",
            external_id="ext",
            status="success",
        )
    )
    db.commit()

    entry = queue_sync(
        db=db,
        user_id=user.id,
        item_type="todo",
        item_id="7",
        content_hash="todo-hash",
        target_name="notion-todos",
    )

    assert entry is None
    assert db.query(SyncQueue).count() == 0


# ------------------------------------------------------------------ metadata sync


def _open_request(i: int) -> UpdateMetadataRequest:
    return UpdateMetadataRequest(
        notebook_uuid=NB_UUID,
        visible_name="Growth",
        document_type="notebook",
        last_opened=(NOW + timedelta(minutes=i)).isoformat() + "Z",
    )


@pytest.mark.asyncio
async def test_metadata_update_makes_no_notion_call_and_coalesces(db, user, notion_config):
    with patch("app.integrations.registry.NotionSyncTarget") as target_cls, \
         patch("app.integrations.notion_sync.NotionClient") as client_cls, \
         patch.object(IntegrationConfig, "get_config", return_value=NOTION_CONFIG):
        for i in range(10):
            response = await update_notebook_metadata(
                request=_open_request(i), current_user=user, db=db
            )
            assert response.success

    target_cls.assert_not_called()
    client_cls.assert_not_called()
    items = db.query(SyncQueue).all()
    assert len(items) == 1
    assert items[0].item_type == "notebook_metadata"
    assert items[0].notebook_uuid == NB_UUID
    assert items[0].status == "pending"


def test_queue_metadata_skips_users_without_notion(db, user, notebook):
    assert queue_notebook_metadata_sync(db, notebook) == []
    assert db.query(SyncQueue).count() == 0


def _target(result):
    """A Notion target whose metadata write returns ``result``."""
    target = MagicMock()
    target.sync_item = AsyncMock(return_value=result)
    return target


SUCCESS = SyncResult(status=SyncStatus.SUCCESS, target_id="notion-page-1")


async def _run_worker(db):
    worker = SyncWorker()
    with patch("app.services.sync_worker.SessionLocal", return_value=db), \
         patch.object(db, "close"):
        await worker._process_pending_items()


@pytest.mark.asyncio
async def test_ten_opens_leave_one_metadata_record(db, user, notion_config):
    target = _target(SUCCESS)

    with patch("app.integrations.registry.NotionSyncTarget", return_value=target), \
         patch.object(IntegrationConfig, "get_config", return_value=NOTION_CONFIG):
        for i in range(10):
            await update_notebook_metadata(request=_open_request(i), current_user=user, db=db)
            await _run_worker(db)

    records = db.query(SyncRecord).filter(SyncRecord.item_type == "notebook_metadata").all()
    assert len(records) == 1
    assert records[0].notebook_uuid == NB_UUID
    assert records[0].external_id == "notion-page-1"
    assert records[0].status == "success"

    # Each open changed lastOpened, so each was pushed.
    assert target.sync_item.await_count == 10
    statuses = {q.status for q in db.query(SyncQueue)}
    assert statuses == {"completed"}


@pytest.mark.asyncio
async def test_unchanged_metadata_is_not_pushed_again(db, user, notion_config):
    target = _target(SUCCESS)

    with patch("app.integrations.registry.NotionSyncTarget", return_value=target), \
         patch.object(IntegrationConfig, "get_config", return_value=NOTION_CONFIG):
        for _ in range(3):
            await update_notebook_metadata(request=_open_request(0), current_user=user, db=db)
            await _run_worker(db)

    assert target.sync_item.await_count == 1
    assert db.query(SyncQueue).count() == 1


@pytest.mark.asyncio
async def test_worker_skips_row_whose_metadata_is_already_written(db, user, notion_config, notebook):
    """Two rows for one notebook (e.g. one queued while the other ran): the second
    finds the record already holds this metadata and makes no call."""
    target = _target(SUCCESS)
    rows = [
        SyncQueue(
            user_id=user.id, item_type="notebook_metadata", item_id=NB_UUID,
            notebook_uuid=NB_UUID, content_hash=f"queued-{i}", target_name="notion",
            status="pending", priority=5, scheduled_at=NOW,
        )
        for i in range(2)
    ]
    db.add_all(rows)
    db.commit()

    with patch("app.integrations.registry.NotionSyncTarget", return_value=target), \
         patch.object(IntegrationConfig, "get_config", return_value=NOTION_CONFIG):
        await _run_worker(db)

    assert target.sync_item.await_count == 1
    assert {q.status for q in db.query(SyncQueue)} == {"completed"}
    assert db.query(SyncRecord).filter(SyncRecord.item_type == "notebook_metadata").count() == 1


@pytest.mark.asyncio
async def test_record_written_meanwhile_by_another_worker_is_updated(db, user, notion_config, notebook):
    """Another worker creates the notebook's record while this one calls Notion:
    the upsert updates that record instead of violating uq_sync_notebook_metadata."""
    async def other_worker_finishes_first(item):
        db.add(
            SyncRecord(
                user_id=user.id, target_name="notion", item_type="notebook_metadata",
                item_id=NB_UUID, notebook_uuid=NB_UUID, content_hash="older",
                external_id="notion-page-1", status="success",
            )
        )
        db.commit()
        return SUCCESS

    target = MagicMock()
    target.sync_item = AsyncMock(side_effect=other_worker_finishes_first)
    row = SyncQueue(
        user_id=user.id, item_type="notebook_metadata", item_id=NB_UUID,
        notebook_uuid=NB_UUID, content_hash="queued", target_name="notion",
        status="pending", priority=5, scheduled_at=NOW,
    )
    db.add(row)
    db.commit()

    with patch("app.integrations.registry.NotionSyncTarget", return_value=target), \
         patch.object(IntegrationConfig, "get_config", return_value=NOTION_CONFIG):
        await _run_worker(db)

    db.expire_all()
    record = db.query(SyncRecord).filter(SyncRecord.item_type == "notebook_metadata").one()
    assert record.content_hash == target.sync_item.await_args.args[0].content_hash
    assert db.query(SyncQueue).one().status == "completed"


@pytest.mark.asyncio
async def test_notebook_not_in_notion_is_skipped_without_record(db, user, notion_config):
    target = _target(SyncResult(status=SyncStatus.SKIPPED, metadata={"reason": "not synced"}))

    with patch("app.integrations.registry.NotionSyncTarget", return_value=target), \
         patch.object(IntegrationConfig, "get_config", return_value=NOTION_CONFIG):
        await update_notebook_metadata(request=_open_request(0), current_user=user, db=db)
        await _run_worker(db)

    target.sync_item.assert_awaited_once()
    assert db.query(SyncRecord).filter(SyncRecord.item_type == "notebook_metadata").count() == 0
    assert db.query(SyncQueue).one().status == "completed"


@pytest.mark.asyncio
async def test_failed_properties_update_is_retried(db, user, notion_config):
    target = _target(
        SyncResult(status=SyncStatus.RETRY, error_message="Failed to update Notion page metadata")
    )

    with patch("app.integrations.registry.NotionSyncTarget", return_value=target), \
         patch.object(IntegrationConfig, "get_config", return_value=NOTION_CONFIG):
        await update_notebook_metadata(request=_open_request(0), current_user=user, db=db)
        await _run_worker(db)

        item = db.query(SyncQueue).one()
        assert item.status == "pending"
        assert item.retry_count == 1
        assert item.scheduled_at > datetime.utcnow()

        # Another open while the row waits for its retry reuses it and keeps
        # the backoff.
        scheduled_at = item.scheduled_at
        await update_notebook_metadata(request=_open_request(1), current_user=user, db=db)

    item = db.query(SyncQueue).one()
    assert (item.status, item.retry_count, item.scheduled_at) == ("pending", 1, scheduled_at)
    assert db.query(SyncRecord).filter(SyncRecord.item_type == "notebook_metadata").count() == 0


# ------------------------------------------------------------------ /health


def test_health_queue_counts_are_capped(db, user, monkeypatch):
    for i in range(5):
        _queue_row(db, user, "pending", i)
    _queue_row(db, user, "failed", 1)
    monkeypatch.setattr(main_module, "HEALTH_QUEUE_COUNT_CAP", 3)

    assert main_module._capped_queue_count(db, "pending") == 3
    assert main_module._capped_queue_count(db, "failed") == 1


# ------------------------------------------------------------------ migration b4e7d2a9c1f3


def test_migration_adds_metadata_index_without_deleting_records():
    import importlib.util
    from pathlib import Path

    import sqlalchemy as sa
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    import app.models  # noqa: F401
    from app.database import Base

    path = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/b4e7d2a9c1f3_unique_notebook_metadata_sync_record.py"
    )
    spec = importlib.util.spec_from_file_location("metadata_index", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def run(fn):
        with engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                getattr(module, fn)()

    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime.utcnow()
    with engine.begin() as conn:
        conn.execute(sa.text("DROP INDEX uq_sync_notebook_metadata"))
        conn.execute(
            sa.text(
                "INSERT INTO users (id, email, is_active, is_verified, subscription_tier, "
                "onboarding_state, agent_token_version, created_at, updated_at) VALUES "
                "(1, 'a@example.com', 1, 1, 'free', 'signed_up', 0, :now, :now)"
            ),
            {"now": now},
        )
        for id, nb, age in [(1, "NB", 2), (2, "NB", 1), (3, None, 0), (4, None, 0)]:
            conn.execute(
                sa.text(
                    "INSERT INTO sync_records (id, user_id, target_name, item_type, item_id, "
                    "content_hash, external_id, status, retry_count, notebook_uuid, "
                    "created_at, updated_at) VALUES (:id, 1, 'notion', 'notebook_metadata', "
                    "'NB', :hash, 'x', 'success', 0, :nb, :ts, :ts)"
                ),
                {"id": id, "hash": f"h{id}", "nb": nb, "ts": now - timedelta(days=age)},
            )

    run("upgrade")

    with engine.connect() as conn:
        rows = conn.execute(sa.text("SELECT id, notebook_uuid FROM sync_records ORDER BY id")).all()
    assert [tuple(r) for r in rows] == [(1, None), (2, "NB"), (3, None), (4, None)]
    indexes = {i["name"]: i for i in sa.inspect(engine).get_indexes("sync_records")}
    assert indexes["uq_sync_notebook_metadata"]["unique"]

    run("downgrade")
    assert "uq_sync_notebook_metadata" not in {
        i["name"] for i in sa.inspect(engine).get_indexes("sync_records")
    }
    run("upgrade")
    engine.dispose()


# ------------------------------------------------------------------ queue_sync callers


def test_enqueue_after_ocr_counts_nothing_when_page_already_in_sync(db, user, notion_config, notebook, caplog):
    """queue_sync returns None for a page already synced with this text; the
    upload/OCR follow-up must treat that as 'nothing to do', not as an error."""
    from app.models.page import Page
    from app.services.fingerprinting import fingerprint_page
    from app.services.page_events import enqueue_integration_syncs

    page_uuid = "0b0b0b0b-0000-4000-8000-0000000000aa"
    page = Page(notebook_id=notebook.id, page_uuid=page_uuid, ocr_status="completed", ocr_text="hello")
    db.add(page)
    db.add(
        SyncRecord(
            user_id=user.id, target_name="notion", item_type="page_text", item_id="1",
            page_uuid=page_uuid, notebook_uuid=NB_UUID, external_id="block",
            content_hash=fingerprint_page(NB_UUID, 0, "hello", page_uuid), status="success",
        )
    )
    db.commit()

    with caplog.at_level("ERROR", logger="app.services.page_events"):
        assert enqueue_integration_syncs(db, page, notebook) == 0
    assert not caplog.records
    assert db.query(SyncQueue).count() == 0
