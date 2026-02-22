"""add_beta_user_fields

Revision ID: a1b2c3d4e5f6
Revises: e8f9a1b2c3d4
Create Date: 2026-02-22 19:45:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'e8f9a1b2c3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add beta user fields and flag all existing users as beta."""

    # Add beta columns to users table
    op.add_column('users', sa.Column('is_beta_user', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('beta_enrolled_at', sa.DateTime(), nullable=True))

    # Flag ALL existing users as beta
    dialect = op.get_bind().dialect.name
    if dialect == 'sqlite':
        op.execute("UPDATE users SET is_beta_user = 1, beta_enrolled_at = CURRENT_TIMESTAMP")
    else:
        op.execute("UPDATE users SET is_beta_user = true, beta_enrolled_at = CURRENT_TIMESTAMP")

    # Update existing free-tier quota records to 200
    op.execute(
        'UPDATE quota_usage SET "limit" = 200 '
        'WHERE user_id IN (SELECT id FROM users) AND "limit" = 30'
    )


def downgrade() -> None:
    """Remove beta user fields and revert quota limits."""

    # Revert quota limits back to 30
    op.execute(
        'UPDATE quota_usage SET "limit" = 30 '
        'WHERE user_id IN (SELECT id FROM users WHERE is_beta_user = 1) AND "limit" = 200'
    )

    op.drop_column('users', 'beta_enrolled_at')
    op.drop_column('users', 'is_beta_user')
