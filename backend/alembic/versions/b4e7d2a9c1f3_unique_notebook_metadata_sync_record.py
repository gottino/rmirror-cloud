"""unique notebook metadata sync record

Revision ID: b4e7d2a9c1f3
Revises: 4f1c2b7d9a3e
Create Date: 2026-11-11

Notebook metadata syncs (title, path, last opened) used to be stored keyed by
a hash that includes ``last_opened``, so every open on the tablet added a
``sync_records`` row. The sync worker now keeps one record per
``(user_id, target_name, notebook_uuid)`` with ``item_type =
'notebook_metadata'``; this partial unique index enforces that.

Records written by the old code have ``notebook_uuid`` NULL (the uuid is in
``item_id``) and never conflict, so they are left as they are. Should two
records with the same non-NULL key exist, ``notebook_uuid`` is cleared on all
but the most recently updated (then highest id) one, which makes them look
like those old records; no row is deleted.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4e7d2a9c1f3"
down_revision: Union[str, Sequence[str], None] = "4f1c2b7d9a3e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "uq_sync_notebook_metadata"


def _detach_duplicates(connection) -> int:
    groups = connection.execute(
        sa.text(
            """
            SELECT user_id, target_name, notebook_uuid
            FROM sync_records
            WHERE item_type = 'notebook_metadata' AND notebook_uuid IS NOT NULL
            GROUP BY user_id, target_name, notebook_uuid
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()

    detached = 0
    for user_id, target_name, notebook_uuid in groups:
        ids = [
            row.id
            for row in connection.execute(
                sa.text(
                    """
                    SELECT id FROM sync_records
                    WHERE item_type = 'notebook_metadata'
                      AND user_id = :user_id
                      AND target_name = :target_name
                      AND notebook_uuid = :notebook_uuid
                    ORDER BY updated_at DESC, id DESC
                    """
                ),
                {"user_id": user_id, "target_name": target_name, "notebook_uuid": notebook_uuid},
            )
        ]
        for record_id in ids[1:]:
            connection.execute(
                sa.text("UPDATE sync_records SET notebook_uuid = NULL WHERE id = :id"),
                {"id": record_id},
            )
            detached += 1
    return detached


def upgrade() -> None:
    detached = _detach_duplicates(op.get_bind())
    if detached:
        print(f"Detached {detached} duplicate notebook_metadata sync_records rows")

    # Partial indexes with IF NOT EXISTS work on PostgreSQL and SQLite.
    op.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {INDEX_NAME} "
        "ON sync_records (user_id, target_name, notebook_uuid) "
        "WHERE item_type = 'notebook_metadata'"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
