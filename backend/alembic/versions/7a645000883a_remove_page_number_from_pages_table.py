"""remove page_number from pages table

Revision ID: 7a645000883a
Revises: 68e211d4af84
Create Date: 2025-12-25 18:12:41.895657

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7a645000883a'
down_revision: Union[str, Sequence[str], None] = '68e211d4af84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove page_number column from pages table.

    The notebook_pages mapping table is now the single source of truth
    for page ordering. The page_number column in pages table is redundant
    and was causing bugs due to stale data.
    """
    # Drop the page_number column
    op.drop_column('pages', 'page_number')


def downgrade() -> None:
    """Re-add page_number column to pages table."""
    # Add back the column (nullable initially)
    op.add_column('pages', sa.Column('page_number', sa.Integer(), nullable=True))

    # Populate it from the mapping table
    op.execute("""
        UPDATE pages
        SET page_number = np.page_number
        FROM notebook_pages np
        WHERE pages.id = np.page_id
    """)

    # Make it non-nullable
    op.alter_column('pages', 'page_number', nullable=False)
