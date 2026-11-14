"""Concurrent find-or-create of one notebook on PostgreSQL produces one row.

Needs a PostgreSQL database migrated to head; set ``TEST_POSTGRES_URL`` to it.
Skipped otherwise (the default SQLite unit run). The CI job
``backend-migrations`` runs it after ``alembic upgrade head``.

Transaction A inserts the notebook and holds its transaction open. Meanwhile
worker B runs the real metadata service for the same notebook in a thread.
With a query-then-insert, B finds nothing (A has not committed) and inserts a
second row. With the upsert, B's insert waits for A, sees the conflict once A
commits, and loads A's row.
"""

import os
import threading
import uuid
from datetime import datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from app.core.notebook_metadata_service import NotebookMetadataService
from app.models.notebook import Notebook

POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL not set")


@pytest.fixture
def pg():
    engine = sa.create_engine(POSTGRES_URL)
    email = f"concurrency-{uuid.uuid4().hex}@example.com"
    with engine.begin() as conn:
        user_id = conn.execute(
            sa.text(
                "INSERT INTO users (email, is_active, is_verified, subscription_tier, "
                "onboarding_state, agent_token_version, created_at, updated_at) VALUES "
                "(:email, true, true, 'free', 'signed_up', 0, :now, :now) RETURNING id"
            ),
            {"email": email, "now": datetime.utcnow()},
        ).scalar_one()
    yield engine, user_id
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    engine.dispose()


def test_two_concurrent_creates_produce_one_notebook(pg):
    engine, user_id = pg
    Session = sessionmaker(bind=engine)
    notebook_uuid = f"nb-{uuid.uuid4().hex}"

    a = engine.connect()
    tx = a.begin()
    a.execute(
        sa.text(
            "INSERT INTO notebooks (user_id, notebook_uuid, visible_name, document_type, "
            "pinned, deleted, created_at, updated_at) VALUES "
            "(:user_id, :uuid, 'From A', 'notebook', false, false, :now, :now)"
        ),
        {"user_id": user_id, "uuid": notebook_uuid, "now": datetime.utcnow()},
    )

    outcome = {}

    def worker_b():
        session = Session()
        try:
            notebook = NotebookMetadataService(session, user_id).update_single_notebook_metadata(
                notebook_uuid, "From B", None, "notebook"
            )
            outcome["id"] = notebook.id
        except Exception as exc:  # reported by the assertion below
            outcome["error"] = exc
            session.rollback()
        finally:
            session.close()

    thread = threading.Thread(target=worker_b)
    thread.start()
    thread.join(timeout=2)  # B is either blocked on A's row or already done
    tx.commit()
    a.close()
    thread.join(timeout=30)
    assert not thread.is_alive()

    assert "error" not in outcome, outcome.get("error")
    with Session() as check:
        rows = check.query(Notebook).filter_by(user_id=user_id, notebook_uuid=notebook_uuid).all()
    assert len(rows) == 1
    assert outcome["id"] == rows[0].id
    assert rows[0].visible_name == "From B"
