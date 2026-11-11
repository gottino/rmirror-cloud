"""todo soft removal

Revision ID: c3d8e1f2a4b6
Revises: b4e7d2a9c1f3
Create Date: 2026-11-11

Todos are extracted automatically after every OCR. A todo that is no longer on
its page, or that the user deletes in the dashboard, is marked removed
(``removed_at``, ``removed_reason``) instead of being deleted, so re-extracting
the page does not create it (and its Todoist or Notion task) again. Both
columns are nullable; existing rows stay live.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d8e1f2a4b6"
down_revision: Union[str, Sequence[str], None] = "b4e7d2a9c1f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("todos", sa.Column("removed_at", sa.DateTime(), nullable=True))
    op.add_column("todos", sa.Column("removed_reason", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("todos", "removed_reason")
    op.drop_column("todos", "removed_at")
