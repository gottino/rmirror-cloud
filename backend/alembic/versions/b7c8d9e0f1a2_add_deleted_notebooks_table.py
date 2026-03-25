"""add deleted_notebooks table

Revision ID: b7c8d9e0f1a2
Revises: 30f649af594a
Create Date: 2026-03-25 19:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, Sequence[str], None] = '30f649af594a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'deleted_notebooks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('notebook_uuid', sa.String(length=255), nullable=False),
        sa.Column('visible_name', sa.String(length=500), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'notebook_uuid', name='uq_deleted_notebook_user_uuid'),
    )
    op.create_index(op.f('ix_deleted_notebooks_id'), 'deleted_notebooks', ['id'], unique=False)
    op.create_index(op.f('ix_deleted_notebooks_user_id'), 'deleted_notebooks', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_deleted_notebooks_user_id'), table_name='deleted_notebooks')
    op.drop_index(op.f('ix_deleted_notebooks_id'), table_name='deleted_notebooks')
    op.drop_table('deleted_notebooks')
