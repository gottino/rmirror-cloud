"""add notebook_pages mapping table

Revision ID: 68e211d4af84
Revises: b6eb40036a86
Create Date: 2025-12-25 13:03:09.431908

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '68e211d4af84'
down_revision: Union[str, Sequence[str], None] = 'b6eb40036a86'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create notebook_pages mapping table
    op.create_table(
        'notebook_pages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('notebook_id', sa.Integer(), nullable=False),
        sa.Column('page_id', sa.Integer(), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['notebook_id'], ['notebooks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('notebook_id', 'page_id', name='uq_notebook_page'),
        sa.UniqueConstraint('notebook_id', 'page_number', name='uq_notebook_page_number')
    )

    # Create indices for performance
    op.create_index('ix_notebook_pages_notebook_id', 'notebook_pages', ['notebook_id'])
    op.create_index('ix_notebook_pages_page_id', 'notebook_pages', ['page_id'])

    # Add content_json column to notebooks table to store .content file data
    op.add_column('notebooks', sa.Column('content_json', sa.Text(), nullable=True))

    # Populate notebook_pages from existing pages.notebook_id relationships
    # This preserves current data while we transition
    # Use DISTINCT ON to handle any remaining duplicates (keep first occurrence)
    op.execute("""
        INSERT INTO notebook_pages (notebook_id, page_id, page_number)
        SELECT notebook_id, id, page_number
        FROM pages
        WHERE notebook_id IS NOT NULL
        AND id IN (
            SELECT MIN(id)
            FROM pages
            WHERE notebook_id IS NOT NULL
            GROUP BY notebook_id, page_number
        )
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('notebooks', 'content_json')
    op.drop_index('ix_notebook_pages_page_id')
    op.drop_index('ix_notebook_pages_notebook_id')
    op.drop_table('notebook_pages')
