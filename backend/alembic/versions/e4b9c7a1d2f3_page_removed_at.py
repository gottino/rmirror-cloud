"""page removed_at

Revision ID: e4b9c7a1d2f3
Revises: d7a3f9c2e5b1
Create Date: 2026-11-23

A page deleted on the tablet (marked deleted in the notebook's ``.content``,
or no longer listed) is soft-removed: ``removed_at`` is set and the page is
hidden everywhere pages are shown. Listing it again clears it; the sync worker
purges pages removed for longer than the retention period. Existing rows stay
NULL (live).
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4b9c7a1d2f3"
down_revision: Union[str, Sequence[str], None] = "d7a3f9c2e5b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pages", sa.Column("removed_at", sa.DateTime(), nullable=True))
    op.create_index("ix_pages_removed_at", "pages", ["removed_at"])


def downgrade() -> None:
    op.drop_index("ix_pages_removed_at", table_name="pages")
    op.drop_column("pages", "removed_at")
