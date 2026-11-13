"""Two workers finishing notebook_metadata rows for one notebook on PostgreSQL.

Needs a PostgreSQL database migrated to head; set ``TEST_POSTGRES_URL`` to it.
Skipped otherwise (the default SQLite unit run). The CI job
``backend-migrations`` runs it after ``alembic upgrade head``.

Both workers call the target at the same time (a barrier holds them until
both are there), so neither sees the other's record before writing its own.
``sync_records`` allows one notebook_metadata record per (user, target,
notebook_uuid) (partial unique index ``uq_sync_notebook_metadata``); the
worker upserts against it, so neither fails and one record remains.
"""

import asyncio
import os
import threading
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from app.core.sync_engine import SyncResult
from app.models.sync_record import IntegrationConfig, SyncQueue, SyncRecord, SyncStatus
from app.services.sync_worker import SyncWorker

POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL not set")


@pytest.fixture
def pg():
    engine = sa.create_engine(POSTGRES_URL)
    Session = sessionmaker(bind=engine)
    now = datetime.utcnow()
    nb_uuid = str(uuid.uuid4())
    with engine.begin() as conn:
        user_id = conn.execute(
            sa.text(
                "INSERT INTO users (email, is_active, is_verified, subscription_tier, "
                "onboarding_state, agent_token_version, created_at, updated_at) VALUES "
                "(:email, true, true, 'free', 'signed_up', 0, :now, :now) RETURNING id"
            ),
            {"email": f"metadata-record-{uuid.uuid4().hex}@example.com", "now": now},
        ).scalar_one()
        conn.execute(
            sa.text(
                "INSERT INTO notebooks (user_id, notebook_uuid, visible_name, document_type, "
                "pinned, deleted, created_at, updated_at) VALUES "
                "(:user_id, :uuid, 'Race', 'notebook', false, false, :now, :now)"
            ),
            {"user_id": user_id, "uuid": nb_uuid, "now": now},
        )
    with Session() as s:
        s.add(IntegrationConfig(user_id=user_id, target_name="notion", is_enabled=True, config_encrypted="x"))
        for i in range(2):
            s.add(
                SyncQueue(
                    user_id=user_id, item_type="notebook_metadata", item_id=nb_uuid,
                    notebook_uuid=nb_uuid, content_hash=f"queued-{i}", target_name="notion",
                    status="processing", priority=5, scheduled_at=now - timedelta(minutes=1),
                )
            )
        s.commit()
    yield Session, user_id, nb_uuid
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    engine.dispose()


def test_two_workers_same_notebook_keep_one_record(pg):
    Session, user_id, nb_uuid = pg
    barrier = threading.Barrier(2, timeout=10)

    async def sync_item(item):
        await asyncio.to_thread(barrier.wait)
        return SyncResult(status=SyncStatus.SUCCESS, target_id="notion-page")

    target = MagicMock()
    target.sync_item = sync_item
    errors = []

    def worker(row_id):
        session = Session()
        try:
            row = session.get(SyncQueue, row_id)
            asyncio.run(SyncWorker()._process_queue_item(session, row))
        except Exception as exc:  # reported by the assertion below
            errors.append(exc)
        finally:
            session.close()

    with Session() as s:
        row_ids = [r.id for r in s.query(SyncQueue).filter_by(user_id=user_id)]

    with patch("app.integrations.registry.NotionSyncTarget", return_value=target), \
         patch.object(IntegrationConfig, "get_config", return_value={"access_token": "t", "database_id": "d"}):
        threads = [threading.Thread(target=worker, args=(row_id,)) for row_id in row_ids]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

    assert errors == []
    with Session() as s:
        records = s.query(SyncRecord).filter_by(user_id=user_id, item_type="notebook_metadata").all()
        statuses = {r.status for r in s.query(SyncQueue).filter_by(user_id=user_id)}
    assert len(records) == 1
    assert records[0].notebook_uuid == nb_uuid and records[0].external_id == "notion-page"
    assert statuses == {"completed"}
