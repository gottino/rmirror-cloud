"""add_folder_structure_to_notebooks

Revision ID: 32a12f25dc9a
Revises: a80ad68daf82
Create Date: 2025-11-06 20:06:03.187921

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '32a12f25dc9a'
down_revision: Union[str, Sequence[str], None] = 'a80ad68daf82'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add folder hierarchy columns
    op.add_column('notebooks', sa.Column('parent_uuid', sa.String(length=255), nullable=True))
    op.add_column('notebooks', sa.Column('full_path', sa.String(length=2000), nullable=True))

    # Add index on parent_uuid for faster folder queries
    op.create_index(op.f('ix_notebooks_parent_uuid'), 'notebooks', ['parent_uuid'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Remove index and columns
    op.drop_index(op.f('ix_notebooks_parent_uuid'), table_name='notebooks')
    op.drop_column('notebooks', 'full_path')
    op.drop_column('notebooks', 'parent_uuid')
