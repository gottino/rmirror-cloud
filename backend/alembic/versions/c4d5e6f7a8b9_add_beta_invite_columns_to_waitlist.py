"""add_beta_invite_columns_to_waitlist

Revision ID: c4d5e6f7a8b9
Revises: b3c7e1f2a4d6
Create Date: 2026-02-11 14:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, Sequence[str], None] = 'b3c7e1f2a4d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add beta invite columns to waitlist table."""
    op.add_column('waitlist', sa.Column('name', sa.String(length=255), nullable=True))
    op.add_column('waitlist', sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'))
    op.add_column('waitlist', sa.Column('invite_token', sa.String(length=512), nullable=True))
    op.add_column('waitlist', sa.Column('approved_at', sa.DateTime(), nullable=True))
    op.add_column('waitlist', sa.Column('claimed_at', sa.DateTime(), nullable=True))
    op.add_column('waitlist', sa.Column('claimed_by', sa.String(length=255), nullable=True))

    op.create_unique_constraint('uq_waitlist_invite_token', 'waitlist', ['invite_token'])


def downgrade() -> None:
    """Remove beta invite columns from waitlist table."""
    op.drop_constraint('uq_waitlist_invite_token', 'waitlist', type_='unique')
    op.drop_column('waitlist', 'claimed_by')
    op.drop_column('waitlist', 'claimed_at')
    op.drop_column('waitlist', 'approved_at')
    op.drop_column('waitlist', 'invite_token')
    op.drop_column('waitlist', 'status')
    op.drop_column('waitlist', 'name')
