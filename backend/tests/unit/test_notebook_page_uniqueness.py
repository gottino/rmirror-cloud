"""Uniqueness of notebooks and pages (migration 4f1c2b7d9a3e and upserts).

The migration tests start from the schema of the previous revision (the model
schema without the three new indexes), insert duplicates, and run the real
``upgrade()``. They use SQLite so they run in CI; the same migration was also
run by hand against PostgreSQL 16, and ``test_concurrent_upserts_postgres.py``
covers real concurrency there.
"""

import importlib.util
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext

from app.core.upserts import get_or_create_notebook, get_or_create_page
from app.database import Base
from app.models.notebook import Notebook
from app.models.page import OcrStatus, Page

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "4f1c2b7d9a3e_unique_notebook_and_page_uuids.py"
)
NEW_INDEXES = (
    "uq_notebooks_user_notebook_uuid",
    "uq_pages_notebook_page_uuid",
    "ix_pages_page_uuid",
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("unique_notebook_page_uuids", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(engine, fn_name: str, module=None) -> None:
    module = module or _load_migration()
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            getattr(module, fn_name)()


def _index_names(engine, table: str) -> set[str]:
    return {idx["name"] for idx in sa.inspect(engine).get_indexes(table)}


@pytest.fixture
def old_db():
    """Schema as of revision 769e64f5a9bb: no uniqueness on notebooks/pages."""
    import app.models  # noqa: F401 - register all tables on Base.metadata

    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for name in NEW_INDEXES:
            conn.execute(sa.text(f"DROP INDEX {name}"))
        conn.execute(
            sa.text(
                "INSERT INTO users (id, email, is_active, is_verified, subscription_tier, "
                "onboarding_state, agent_token_version, created_at, updated_at) VALUES "
                "(1, 'a@example.com', 1, 1, 'free', 'signed_up', 0, :now, :now)"
            ),
            {"now": datetime.utcnow()},
        )
    yield engine
    engine.dispose()


def _notebook(conn, id, uuid="NB", deleted=False, updated_at=None):
    conn.execute(
        sa.text(
            "INSERT INTO notebooks (id, user_id, notebook_uuid, visible_name, document_type, "
            "pinned, deleted, created_at, updated_at) VALUES "
            "(:id, 1, :uuid, 'n', 'notebook', 0, :deleted, :ts, :ts)"
        ),
        dict(id=id, uuid=uuid, deleted=deleted, ts=updated_at or datetime.utcnow()),
    )


def _page(conn, id, notebook_id, page_uuid, status, text=None, s3_key=None, updated_at=None):
    conn.execute(
        sa.text(
            "INSERT INTO pages (id, notebook_id, page_uuid, ocr_status, ocr_text, s3_key, "
            "created_at, updated_at) VALUES "
            "(:id, :nb, :uuid, :status, :text, :s3, :ts, :ts)"
        ),
        dict(
            id=id,
            nb=notebook_id,
            uuid=page_uuid,
            status=status,
            text=text,
            s3=s3_key,
            ts=updated_at or datetime.utcnow(),
        ),
    )


def _ids(engine, sql: str) -> list:
    with engine.connect() as conn:
        return [tuple(r) if len(r) > 1 else r[0] for r in conn.execute(sa.text(sql))]


# ---------------------------------------------------------------- migration


def test_upgrade_creates_the_indexes(old_db):
    _run(old_db, "upgrade")

    indexes = {
        idx["name"]: idx
        for table in ("notebooks", "pages")
        for idx in sa.inspect(old_db).get_indexes(table)
    }
    assert indexes["uq_notebooks_user_notebook_uuid"]["unique"]
    assert indexes["uq_notebooks_user_notebook_uuid"]["column_names"] == ["user_id", "notebook_uuid"]
    assert indexes["uq_pages_notebook_page_uuid"]["unique"]
    assert indexes["uq_pages_notebook_page_uuid"]["column_names"] == ["notebook_id", "page_uuid"]
    assert not indexes["ix_pages_page_uuid"]["unique"]
    assert indexes["ix_pages_page_uuid"]["column_names"] == ["page_uuid"]


def test_upgrade_merges_duplicate_pages_and_keeps_their_children(old_db):
    now = datetime.utcnow()
    with old_db.begin() as conn:
        _notebook(conn, 10)
        _page(conn, 100, 10, "P", "completed", "T", "k", now - timedelta(days=1))
        _page(conn, 101, 10, "P", "not_synced", None, None, now)
        _page(conn, 102, 10, "P", "completed", "T", "k", now - timedelta(days=2))
        # NULL page_uuid is never deduplicated.
        _page(conn, 103, 10, None, "pending")
        _page(conn, 104, 10, None, "pending")
        conn.execute(
            sa.text(
                "INSERT INTO notebook_pages (notebook_id, page_id, page_number, created_at, "
                "updated_at) VALUES (10, 102, 2, :now, :now)"
            ),
            {"now": now},
        )
        conn.execute(
            sa.text(
                "INSERT INTO todos (user_id, notebook_id, page_id, title, text, completed, "
                "created_at, updated_at) VALUES (1, 10, 101, 't', 'x', 0, :now, :now)"
            ),
            {"now": now},
        )

    _run(old_db, "upgrade")

    assert _ids(old_db, "SELECT id FROM pages ORDER BY id") == [100, 103, 104]
    # The mapping and the todo of merged rows now point at the kept row.
    assert _ids(old_db, "SELECT page_id, page_number FROM notebook_pages") == [(100, 2)]
    assert _ids(old_db, "SELECT page_id FROM todos") == [100]


def test_upgrade_removes_empty_duplicate_notebooks(old_db):
    now = datetime.utcnow()
    with old_db.begin() as conn:
        _notebook(conn, 10, updated_at=now - timedelta(days=5))
        _page(conn, 100, 10, "P", "completed", "T")
        _notebook(conn, 11, updated_at=now)  # newer, but owns nothing
        _notebook(conn, 12, uuid="OTHER")

    _run(old_db, "upgrade")

    assert _ids(old_db, "SELECT id FROM notebooks ORDER BY id") == [10, 12]


def test_upgrade_refuses_to_drop_differing_ocr_text(old_db):
    module = _load_migration()
    with old_db.begin() as conn:
        _notebook(conn, 10)
        _page(conn, 100, 10, "P", "completed", "first text")
        _page(conn, 101, 10, "P", "completed", "second text")

    with pytest.raises(module.UnresolvedDuplicatesError, match="differing OCR text"):
        _run(old_db, "upgrade", module)

    # Rolled back: nothing deleted, no index created.
    assert _ids(old_db, "SELECT id FROM pages ORDER BY id") == [100, 101]
    assert "uq_pages_notebook_page_uuid" not in _index_names(old_db, "pages")


def test_upgrade_refuses_to_drop_notebooks_that_own_content(old_db):
    module = _load_migration()
    with old_db.begin() as conn:
        _notebook(conn, 10)
        _page(conn, 100, 10, "P", "completed", "T")
        _notebook(conn, 11)
        _page(conn, 110, 11, "Q", "completed", "U")

    with pytest.raises(module.UnresolvedDuplicatesError, match="notebook group"):
        _run(old_db, "upgrade", module)

    assert _ids(old_db, "SELECT id FROM notebooks ORDER BY id") == [10, 11]


def test_downgrade_then_upgrade(old_db):
    _run(old_db, "upgrade")
    _run(old_db, "downgrade")
    assert not set(NEW_INDEXES) & (_index_names(old_db, "notebooks") | _index_names(old_db, "pages"))
    _run(old_db, "upgrade")
    assert set(NEW_INDEXES) <= _index_names(old_db, "notebooks") | _index_names(old_db, "pages")


# ---------------------------------------------------------------- upserts


def test_unique_index_rejects_a_second_notebook_row(db, test_user):
    for _ in range(2):
        db.add(
            Notebook(
                user_id=test_user.id, notebook_uuid="same", visible_name="n", document_type="notebook"
            )
        )
    with pytest.raises(sa.exc.IntegrityError):
        db.commit()


def test_get_or_create_notebook_returns_existing_row(db, test_user):
    first, created = get_or_create_notebook(
        db, test_user.id, "nb-1", visible_name="First", document_type="notebook"
    )
    db.commit()
    assert created

    second, created_again = get_or_create_notebook(
        db, test_user.id, "nb-1", visible_name="Second", document_type="notebook"
    )
    db.commit()

    assert not created_again
    assert second.id == first.id
    # create values apply only on insert
    assert second.visible_name == "First"
    assert db.query(Notebook).filter_by(notebook_uuid="nb-1").count() == 1


def test_get_or_create_page_returns_existing_row(db, test_user):
    notebook, _ = get_or_create_notebook(
        db, test_user.id, "nb-1", visible_name="n", document_type="notebook"
    )
    page, created = get_or_create_page(db, notebook.id, "p-1", ocr_status=OcrStatus.NOT_SYNCED)
    again, created_again = get_or_create_page(db, notebook.id, "p-1", ocr_status=OcrStatus.PENDING)
    db.commit()

    assert created and not created_again
    assert again.id == page.id
    assert again.ocr_status == OcrStatus.NOT_SYNCED
    assert db.query(Page).filter_by(page_uuid="p-1").count() == 1

