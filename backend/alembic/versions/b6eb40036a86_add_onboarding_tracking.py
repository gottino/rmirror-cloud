"""add_onboarding_tracking

Revision ID: b6eb40036a86
Revises: 3882fe98be5f
Create Date: 2025-12-15 21:18:09.848128

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b6eb40036a86'
down_revision: Union[str, Sequence[str], None] = '3882fe98be5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add onboarding tracking columns to users table
    op.add_column('users', sa.Column('onboarding_state', sa.String(length=30), nullable=False, server_default='signed_up'))
    op.add_column('users', sa.Column('onboarding_started_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('onboarding_completed_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('agent_downloaded_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('agent_first_connected_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove onboarding tracking columns
    op.drop_column('users', 'agent_first_connected_at')
    op.drop_column('users', 'agent_downloaded_at')
    op.drop_column('users', 'onboarding_completed_at')
    op.drop_column('users', 'onboarding_started_at')
    op.drop_column('users', 'onboarding_state')
