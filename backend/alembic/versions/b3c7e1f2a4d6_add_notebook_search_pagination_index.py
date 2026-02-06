"""add_notebook_search_pagination_index

Revision ID: b3c7e1f2a4d6
Revises: f8a2b4c9d1e7
Create Date: 2026-02-06 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b3c7e1f2a4d6'
down_revision: Union[str, Sequence[str], None] = 'f8a2b4c9d1e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add partial composite index for search pagination queries.

    The two-phase search query filters WHERE user_id = X AND deleted = false,
    then orders by updated_at DESC. This partial index excludes soft-deleted
    records, making it smaller and faster than a full composite index.

    PostgreSQL only - SQLite skips this.
    """
    conn = op.get_bind()
    if conn.dialect.name == 'postgresql':
        op.execute(sa.text("""
            CREATE INDEX IF NOT EXISTS idx_notebooks_user_deleted_updated
            ON notebooks (user_id, updated_at DESC)
            WHERE deleted = false
        """))


def downgrade() -> None:
    """Remove the search pagination index."""
    conn = op.get_bind()
    if conn.dialect.name == 'postgresql':
        op.execute(sa.text("DROP INDEX IF EXISTS idx_notebooks_user_deleted_updated"))
