"""add pdf_dirty_at to notebooks for debounced pdf rebuild

Revision ID: 363cfc77dfe8
Revises: b7c8d9e0f1a2
Create Date: 2026-06-05 10:28:06.358254

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '363cfc77dfe8'
down_revision: Union[str, Sequence[str], None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Marks a notebook whose combined PDF needs a rebuild. Set on each page
    # upload; the background worker debounces and rebuilds once the value is
    # older than the debounce window, then clears it back to NULL.
    op.add_column(
        "notebooks",
        sa.Column("pdf_dirty_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_notebooks_pdf_dirty_at", "notebooks", ["pdf_dirty_at"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_notebooks_pdf_dirty_at", table_name="notebooks")
    op.drop_column("notebooks", "pdf_dirty_at")
