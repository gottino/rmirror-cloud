"""restore unique page_uuid index on sync_records

Revision ID: 95cf6385d77b
Revises: 363cfc77dfe8
Create Date: 2026-11-10

Migration 51324b8f201a was meant to replace the non-unique
``idx_sync_page_uuid`` with a UNIQUE index on
``(page_uuid, target_name, user_id)``. It read the list of existing indexes,
dropped the old one, then created the new one only if its name was absent
from that list. The list was read before the drop, so the name was always
present and the unique index was never created. A database built with
``alembic upgrade head`` ends up with no index on ``page_uuid`` at all.

The model (``app/models/sync_record.py``) and the tests, which build the
schema from the models, have the unique index, so the gap never showed up in
CI. Without it, duplicate sync records for the same page are possible, and
lookups by ``page_uuid`` scan the table.

This migration:

1. Removes duplicate rows per ``(page_uuid, target_name, user_id)``, keeping
   one row per group: a ``success`` row before any other status, then the
   most recently updated, then the highest id. Rows with a NULL
   ``page_uuid`` (notebook-level and todo records) are not touched; NULLs
   never conflict in a unique index.
2. Drops ``idx_sync_page_uuid`` if any version of it exists.
3. Creates the unique index unconditionally.
"""
from datetime import datetime
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "95cf6385d77b"
down_revision: Union[str, Sequence[str], None] = "363cfc77dfe8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "idx_sync_page_uuid"
INDEX_COLUMNS = ["page_uuid", "target_name", "user_id"]


def _as_datetime(value):
    """Raw SQL returns datetimes on PostgreSQL but ISO strings on SQLite."""
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _keep_order(row) -> tuple:
    """Sort key: the row to keep sorts first."""
    last_touched = (
        _as_datetime(row.updated_at)
        or _as_datetime(row.synced_at)
        or _as_datetime(row.created_at)
    )
    return (
        0 if row.status == "success" else 1,
        # Newest first; rows with no timestamp at all go last.
        0 if last_touched is not None else 1,
        -(last_touched.timestamp() if last_touched is not None else 0),
        -row.id,
    )


def _remove_duplicates(connection) -> int:
    groups = connection.execute(
        sa.text(
            """
            SELECT page_uuid, target_name, user_id
            FROM sync_records
            WHERE page_uuid IS NOT NULL
            GROUP BY page_uuid, target_name, user_id
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()

    removed = 0
    for page_uuid, target_name, user_id in groups:
        rows = connection.execute(
            sa.text(
                """
                SELECT id, status, updated_at, synced_at, created_at
                FROM sync_records
                WHERE page_uuid = :page_uuid
                  AND target_name = :target_name
                  AND user_id = :user_id
                """
            ),
            {"page_uuid": page_uuid, "target_name": target_name, "user_id": user_id},
        ).fetchall()
        rows = sorted(rows, key=_keep_order)
        for row in rows[1:]:
            connection.execute(
                sa.text("DELETE FROM sync_records WHERE id = :id"), {"id": row.id}
            )
            removed += 1
    return removed


def upgrade() -> None:
    connection = op.get_bind()

    removed = _remove_duplicates(connection)
    if removed:
        print(f"Removed {removed} duplicate sync_records rows before adding unique index")

    # IF EXISTS works on PostgreSQL and SQLite, and unlike a try/except around
    # op.drop_index it does not abort the PostgreSQL transaction when the
    # index is missing.
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
    op.create_index(INDEX_NAME, "sync_records", INDEX_COLUMNS, unique=True)


def downgrade() -> None:
    # Return to the state the previous head actually produced: no index.
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
