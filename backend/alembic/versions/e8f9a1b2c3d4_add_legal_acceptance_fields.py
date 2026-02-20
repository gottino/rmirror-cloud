"""add legal acceptance fields

Revision ID: e8f9a1b2c3d4
Revises: d7b15f90002c
Create Date: 2026-02-20 21:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e8f9a1b2c3d4'
down_revision: Union[str, Sequence[str], None] = 'd7b15f90002c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add legal acceptance tracking columns to users table."""
    op.add_column('users', sa.Column('tos_accepted_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('tos_version', sa.String(20), nullable=True))
    op.add_column('users', sa.Column('privacy_accepted_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('privacy_version', sa.String(20), nullable=True))


def downgrade() -> None:
    """Remove legal acceptance tracking columns from users table."""
    op.drop_column('users', 'privacy_version')
    op.drop_column('users', 'privacy_accepted_at')
    op.drop_column('users', 'tos_version')
    op.drop_column('users', 'tos_accepted_at')
