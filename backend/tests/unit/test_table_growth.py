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
from app.services.notebook_metadata_sync import queue_notebook_metadata_sync
from app.services.sync_queue import prune_sync_queue, queue_sync
from app.services.sync_worker import SyncWorker
from tests.conftest import create_user_with_quota

NOW = datetime(2026, 11, 1, 12, 0, 0)
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
        notebook_uuid="nb-growth",
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
        notebook_uuid="nb-growth",
        visible_name="Growth",
        document_type="notebook",
        last_opened=(NOW + timedelta(minutes=i)).isoformat() + "Z",
    )


@pytest.mark.asyncio
async def test_metadata_update_makes_no_notion_call_and_coalesces(db, user, notion_config):
    with patch("app.integrations.notion_sync.NotionSyncTarget") as target_cls, \
         patch.object(IntegrationConfig, "get_config", return_value=NOTION_CONFIG):
        for i in range(10):
            response = await update_notebook_metadata(
                request=_open_request(i), current_user=user, db=db
            )
            assert response.success

    target_cls.assert_not_called()
    items = db.query(SyncQueue).all()
    assert len(items) == 1
    assert items[0].item_type == "notebook_metadata"
    assert items[0].notebook_uuid == "nb-growth"
    assert items[0].status == "pending"


def test_queue_metadata_skips_users_without_notion(db, user, notebook):
    assert queue_notebook_metadata_sync(db, user.id, notebook) == []
    assert db.query(SyncQueue).count() == 0


def _notebook_record(db, user, external_id="notion-page-1"):
    db.add(
        SyncRecord(
            user_id=user.id,
            target_name="notion",
            item_type="notebook",
            item_id="1",
            content_hash="notebook",
            external_id=external_id,
            status="success",
            notebook_uuid="nb-growth",
        )
    )
    db.commit()


async def _run_worker(db):
    worker = SyncWorker()
    with patch("app.services.sync_worker.SessionLocal", return_value=db), \
         patch.object(db, "close"):
        await worker._process_pending_items()


@pytest.mark.asyncio
async def test_ten_opens_leave_one_metadata_record(db, user, notion_config):
    _notebook_record(db, user)
    target = MagicMock()
    target._update_notion_page_properties = AsyncMock(return_value=True)
    target.sync_item = AsyncMock()

    with patch("app.integrations.notion_sync.NotionSyncTarget", return_value=target), \
         patch.object(IntegrationConfig, "get_config", return_value=NOTION_CONFIG):
        for i in range(10):
            await update_notebook_metadata(request=_open_request(i), current_user=user, db=db)
            await _run_worker(db)

    records = db.query(SyncRecord).filter(SyncRecord.item_type == "notebook_metadata").all()
    assert len(records) == 1
    assert records[0].notebook_uuid == "nb-growth"
    assert records[0].external_id == "notion-page-1"
    assert records[0].status == "success"

    # Each open changed lastOpened, so each was pushed, using the stored page id.
    assert target._update_notion_page_properties.await_count == 10
    assert target._update_notion_page_properties.await_args.args[0] == "notion-page-1"
    target.sync_item.assert_not_awaited()
    statuses = {q.status for q in db.query(SyncQueue)}
    assert statuses == {"completed"}


@pytest.mark.asyncio
async def test_unchanged_metadata_is_not_pushed_again(db, user, notion_config):
    _notebook_record(db, user)
    target = MagicMock()
    target._update_notion_page_properties = AsyncMock(return_value=True)

    with patch("app.integrations.notion_sync.NotionSyncTarget", return_value=target), \
         patch.object(IntegrationConfig, "get_config", return_value=NOTION_CONFIG):
        for _ in range(3):
            await update_notebook_metadata(request=_open_request(0), current_user=user, db=db)
            await _run_worker(db)

    assert target._update_notion_page_properties.await_count == 1


@pytest.mark.asyncio
async def test_notebook_not_in_notion_is_skipped_without_record(db, user, notion_config):
    target = MagicMock()
    target._update_notion_page_properties = AsyncMock()
    target.sync_item = AsyncMock(
        return_value=SyncResult(status=SyncStatus.SKIPPED, metadata={"reason": "not synced"})
    )

    with patch("app.integrations.notion_sync.NotionSyncTarget", return_value=target), \
         patch.object(IntegrationConfig, "get_config", return_value=NOTION_CONFIG):
        await update_notebook_metadata(request=_open_request(0), current_user=user, db=db)
        await _run_worker(db)

    target._update_notion_page_properties.assert_not_awaited()
    target.sync_item.assert_awaited_once()
    assert db.query(SyncRecord).filter(SyncRecord.item_type == "notebook_metadata").count() == 0
    assert db.query(SyncQueue).one().status == "completed"


@pytest.mark.asyncio
async def test_failed_properties_update_is_retried(db, user, notion_config):
    _notebook_record(db, user)
    target = MagicMock()
    target._update_notion_page_properties = AsyncMock(return_value=False)

    with patch("app.integrations.notion_sync.NotionSyncTarget", return_value=target), \
         patch.object(IntegrationConfig, "get_config", return_value=NOTION_CONFIG):
        await update_notebook_metadata(request=_open_request(0), current_user=user, db=db)
        await _run_worker(db)

    item = db.query(SyncQueue).one()
    assert item.status == "pending"
    assert item.retry_count == 1
    assert item.scheduled_at > datetime.utcnow()
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
