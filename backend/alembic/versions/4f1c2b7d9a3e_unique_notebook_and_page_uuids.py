"""unique notebook and page uuids

Revision ID: 4f1c2b7d9a3e
Revises: 769e64f5a9bb
Create Date: 2026-11-11

Notebooks and pages were found or created with a query followed by an
insert. Two requests for the same reMarkable document could both miss the
query and both insert, leaving two ``notebooks`` rows for one
``(user_id, notebook_uuid)`` or two ``pages`` rows for one
``(notebook_id, page_uuid)``. Lookups by ``pages.page_uuid`` alone also had
no index.

This migration:

1. Merges duplicate ``pages`` per ``(notebook_id, page_uuid)``. The row kept
   is, in order: ``ocr_status = 'completed'``, then non-empty ``ocr_text``,
   then an uploaded ``.rm`` file (``s3_key``), then the most recently
   updated, then the highest id. Todos and highlights of the other rows are
   moved to the kept row; their ``notebook_pages`` entry is moved too when the
   kept row has none, and dropped otherwise. A group is merged only when its
   rows carry at most one distinct non-empty OCR text, so no OCR text is lost.
2. Removes duplicate ``notebooks`` per ``(user_id, notebook_uuid)`` that own
   nothing (no pages, page mappings, todos or highlights). The row kept is,
   in order: not deleted, then the most pages, then the most recently
   updated, then the highest id.
3. Stops with an error, before any index is created, when duplicates remain
   that cannot be merged without losing content. The transaction is rolled
   back as a whole; nothing is changed. The message names the query that
   lists them so they can be resolved by hand.
4. Creates ``uq_notebooks_user_notebook_uuid``,
   ``uq_pages_notebook_page_uuid`` and ``ix_pages_page_uuid`` (IF NOT EXISTS).

Rows with a NULL ``page_uuid`` are not touched; NULLs never conflict in a
unique index.
"""
from datetime import datetime
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4f1c2b7d9a3e"
down_revision: Union[str, Sequence[str], None] = "769e64f5a9bb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOTEBOOK_INDEX = "uq_notebooks_user_notebook_uuid"
PAGE_UNIQUE_INDEX = "uq_pages_notebook_page_uuid"
PAGE_UUID_INDEX = "ix_pages_page_uuid"

DUPLICATE_PAGES_QUERY = (
    "SELECT notebook_id, page_uuid, COUNT(*) FROM pages "
    "WHERE page_uuid IS NOT NULL GROUP BY notebook_id, page_uuid HAVING COUNT(*) > 1"
)
DUPLICATE_NOTEBOOKS_QUERY = (
    "SELECT user_id, notebook_uuid, COUNT(*) FROM notebooks "
    "GROUP BY user_id, notebook_uuid HAVING COUNT(*) > 1"
)


class UnresolvedDuplicatesError(RuntimeError):
    """Duplicates remain that cannot be merged without losing content."""


def _as_datetime(value):
    """Raw SQL returns datetimes on PostgreSQL but ISO strings on SQLite."""
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _newest_first(value) -> tuple:
    ts = _as_datetime(value)
    return (0 if ts is not None else 1, -(ts.timestamp() if ts is not None else 0))


def _page_keep_order(row) -> tuple:
    """Sort key: the page to keep sorts first."""
    return (
        0 if row.ocr_status == "completed" else 1,
        0 if row.ocr_text else 1,
        0 if row.s3_key else 1,
        *_newest_first(row.updated_at),
        -row.id,
    )


def _merge_duplicate_pages(connection) -> tuple[int, int]:
    """Merge safe duplicate page groups. Returns (removed, unresolved groups)."""
    groups = connection.execute(
        sa.text(
            """
            SELECT notebook_id, page_uuid
            FROM pages
            WHERE page_uuid IS NOT NULL
            GROUP BY notebook_id, page_uuid
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()

    removed = 0
    unresolved = 0
    for notebook_id, page_uuid in groups:
        rows = connection.execute(
            sa.text(
                """
                SELECT id, ocr_status, ocr_text, s3_key, updated_at
                FROM pages
                WHERE notebook_id = :notebook_id AND page_uuid = :page_uuid
                """
            ),
            {"notebook_id": notebook_id, "page_uuid": page_uuid},
        ).fetchall()

        texts = {row.ocr_text for row in rows if row.ocr_text}
        if len(texts) > 1:
            unresolved += 1
            continue

        rows = sorted(rows, key=_page_keep_order)
        keep_id = rows[0].id
        for row in rows[1:]:
            params = {"keep": keep_id, "drop": row.id}
            connection.execute(
                sa.text("UPDATE todos SET page_id = :keep WHERE page_id = :drop"), params
            )
            connection.execute(
                sa.text("UPDATE highlights SET page_id = :keep WHERE page_id = :drop"), params
            )
            keep_has_mapping = connection.execute(
                sa.text("SELECT 1 FROM notebook_pages WHERE page_id = :keep"), params
            ).first()
            if keep_has_mapping:
                connection.execute(
                    sa.text("DELETE FROM notebook_pages WHERE page_id = :drop"), params
                )
            else:
                connection.execute(
                    sa.text("UPDATE notebook_pages SET page_id = :keep WHERE page_id = :drop"),
                    params,
                )
            connection.execute(sa.text("DELETE FROM pages WHERE id = :drop"), params)
            removed += 1
    return removed, unresolved


def _remove_empty_duplicate_notebooks(connection) -> tuple[int, int]:
    """Delete duplicate notebooks that own nothing. Returns (removed, unresolved groups)."""
    groups = connection.execute(
        sa.text(
            """
            SELECT user_id, notebook_uuid
            FROM notebooks
            GROUP BY user_id, notebook_uuid
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()

    removed = 0
    unresolved = 0
    for user_id, notebook_uuid in groups:
        rows = connection.execute(
            sa.text(
                """
                SELECT n.id, n.deleted, n.updated_at,
                       (SELECT COUNT(*) FROM pages p WHERE p.notebook_id = n.id) AS page_count,
                       (SELECT COUNT(*) FROM pages p WHERE p.notebook_id = n.id)
                     + (SELECT COUNT(*) FROM notebook_pages m WHERE m.notebook_id = n.id)
                     + (SELECT COUNT(*) FROM todos t WHERE t.notebook_id = n.id)
                     + (SELECT COUNT(*) FROM highlights h WHERE h.notebook_id = n.id)
                       AS owned
                FROM notebooks n
                WHERE n.user_id = :user_id AND n.notebook_uuid = :notebook_uuid
                """
            ),
            {"user_id": user_id, "notebook_uuid": notebook_uuid},
        ).fetchall()
        rows = sorted(
            rows,
            key=lambda r: (
                1 if r.deleted else 0,
                -r.page_count,
                *_newest_first(r.updated_at),
                -r.id,
            ),
        )
        losers = rows[1:]
        if any(r.owned for r in losers):
            unresolved += 1
            continue
        for row in losers:
            connection.execute(sa.text("DELETE FROM notebooks WHERE id = :id"), {"id": row.id})
            removed += 1
    return removed, unresolved


def upgrade() -> None:
    connection = op.get_bind()

    pages_removed, page_groups_left = _merge_duplicate_pages(connection)
    notebooks_removed, notebook_groups_left = _remove_empty_duplicate_notebooks(connection)

    if page_groups_left or notebook_groups_left:
        # Raised before any DDL; the whole migration rolls back.
        raise UnresolvedDuplicatesError(
            "Cannot add unique indexes: "
            f"{page_groups_left} duplicate page group(s) with differing OCR text, "
            f"{notebook_groups_left} duplicate notebook group(s) that own content. "
            "Resolve them by hand, then rerun. Pages: "
            f"{DUPLICATE_PAGES_QUERY}; notebooks: {DUPLICATE_NOTEBOOKS_QUERY}"
        )

    if pages_removed:
        print(f"Merged {pages_removed} duplicate pages rows before adding unique index")
    if notebooks_removed:
        print(f"Removed {notebooks_removed} empty duplicate notebooks rows before adding unique index")

    # CREATE ... IF NOT EXISTS works on PostgreSQL and SQLite.
    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {NOTEBOOK_INDEX} "
        "ON notebooks (user_id, notebook_uuid)"
    )
    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {PAGE_UNIQUE_INDEX} "
        "ON pages (notebook_id, page_uuid)"
    )
    op.execute(f"CREATE INDEX IF NOT EXISTS {PAGE_UUID_INDEX} ON pages (page_uuid)")


def downgrade() -> None:
    # Merged duplicates are not restored.
    op.execute(f"DROP INDEX IF EXISTS {PAGE_UUID_INDEX}")
    op.execute(f"DROP INDEX IF EXISTS {PAGE_UNIQUE_INDEX}")
    op.execute(f"DROP INDEX IF EXISTS {NOTEBOOK_INDEX}")
