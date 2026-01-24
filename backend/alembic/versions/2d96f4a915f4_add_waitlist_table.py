"""add_waitlist_table

Revision ID: 2d96f4a915f4
Revises: 530f980e31fb
Create Date: 2025-11-22 17:39:42.543226

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '2d96f4a915f4'
down_revision: Union[str, Sequence[str], None] = '530f980e31fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'waitlist',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_waitlist_email'), 'waitlist', ['email'], unique=True)
    op.create_index(op.f('ix_waitlist_id'), 'waitlist', ['id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_waitlist_id'), table_name='waitlist')
    op.drop_index(op.f('ix_waitlist_email'), table_name='waitlist')
    op.drop_table('waitlist')
