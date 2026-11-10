"""Migration 95cf6385d77b restores the unique page_uuid index on sync_records.

Migration 51324b8f201a dropped ``idx_sync_page_uuid`` and, because of a stale
index list, never created its unique replacement. These tests start from that
broken state (table present, index absent, duplicate rows), run the real
``upgrade()``, and check the result. They use SQLite so they run in CI; the
same migration was also run by hand against PostgreSQL 16.
"""

import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

from app.database import Base

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "95cf6385d77b_restore_unique_page_uuid_index_on_sync_.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("restore_page_uuid_index", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(engine, fn_name: str) -> None:
    module = _load_migration()
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            getattr(module, fn_name)()


@pytest.fixture
def broken_db():
    """sync_records as production has it: no index on page_uuid."""
    import app.models  # noqa: F401 - register all tables on Base.metadata

    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("DROP INDEX idx_sync_page_uuid"))
        conn.execute(
            sa.text(
                "INSERT INTO users (id, email, is_active, is_verified, subscription_tier, "
                "onboarding_state, created_at, updated_at) VALUES "
                "(1, 'a@example.com', 1, 1, 'free', 'signed_up', :now, :now), "
                "(2, 'b@example.com', 1, 1, 'free', 'signed_up', :now, :now)"
            ),
            {"now": datetime.utcnow()},
        )
    yield engine
    engine.dispose()


def _insert(conn, id, user_id, target, page_uuid, status, updated_at, external_id):
    conn.execute(
        sa.text(
            "INSERT INTO sync_records (id, user_id, target_name, item_type, item_id, "
            "content_hash, external_id, status, retry_count, page_uuid, created_at, updated_at) "
            "VALUES (:id, :user_id, :target, 'page_text', '1', 'h', :external_id, "
            ":status, 0, :page_uuid, :ts, :ts)"
        ),
        dict(
            id=id,
            user_id=user_id,
            target=target,
            page_uuid=page_uuid,
            status=status,
            ts=updated_at,
            external_id=external_id,
        ),
    )


def _index_info(engine) -> dict | None:
    for idx in sa.inspect(engine).get_indexes("sync_records"):
        if idx["name"] == "idx_sync_page_uuid":
            return idx
    return None


def test_upgrade_creates_unique_index(broken_db):
    assert _index_info(broken_db) is None

    _run(broken_db, "upgrade")

    idx = _index_info(broken_db)
    assert idx is not None
    assert idx["unique"]
    assert idx["column_names"] == ["page_uuid", "target_name", "user_id"]


def test_upgrade_keeps_newest_success_row_per_page(broken_db):
    now = datetime.utcnow()
    with broken_db.begin() as conn:
        _insert(conn, 10, 1, "notion", "P1", "success", now - timedelta(days=3), "blk-old")
        _insert(conn, 11, 1, "notion", "P1", "failed", now, "blk-failed")
        _insert(conn, 12, 1, "notion", "P1", "success", now - timedelta(days=1), "blk-new")
        # Same page, different target or user: not duplicates.
        _insert(conn, 13, 1, "obsidian", "P1", "success", now, "f.md")
        _insert(conn, 14, 2, "notion", "P1", "success", now, "blk-u2")
        # NULL page_uuid (notebook-level records) is never deduplicated.
        _insert(conn, 15, 1, "notion", None, "success", now, "nb-1")
        _insert(conn, 16, 1, "notion", None, "success", now, "nb-1")

    _run(broken_db, "upgrade")

    with broken_db.connect() as conn:
        ids = [r[0] for r in conn.execute(sa.text("SELECT id FROM sync_records ORDER BY id"))]
    assert ids == [12, 13, 14, 15, 16]


def test_duplicate_page_insert_is_rejected_after_upgrade(broken_db):
    now = datetime.utcnow()
    _run(broken_db, "upgrade")

    with broken_db.begin() as conn:
        _insert(conn, 20, 1, "notion", "P9", "success", now, "blk")

    with pytest.raises(sa.exc.IntegrityError, match="UNIQUE constraint failed"):
        with broken_db.begin() as conn:
            _insert(conn, 21, 1, "notion", "P9", "success", now, "blk-dup")


def test_upgrade_replaces_a_non_unique_index_of_the_same_name(broken_db):
    """Databases created before 51324b8f201a still carry the old non-unique index."""
    with broken_db.begin() as conn:
        conn.execute(sa.text("CREATE INDEX idx_sync_page_uuid ON sync_records (page_uuid)"))

    _run(broken_db, "upgrade")

    idx = _index_info(broken_db)
    assert idx["unique"]
    assert idx["column_names"] == ["page_uuid", "target_name", "user_id"]


def test_downgrade_then_upgrade(broken_db):
    _run(broken_db, "upgrade")
    _run(broken_db, "downgrade")
    assert _index_info(broken_db) is None
    _run(broken_db, "upgrade")
    assert _index_info(broken_db)["unique"]
