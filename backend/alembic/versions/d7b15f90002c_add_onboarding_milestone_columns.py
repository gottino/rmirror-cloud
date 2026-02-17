"""add onboarding milestone columns

Revision ID: d7b15f90002c
Revises: c4d5e6f7a8b9
Create Date: 2026-02-17 08:46:38.680222

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7b15f90002c'
down_revision: Union[str, Sequence[str], None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add onboarding milestone tracking columns to users table."""
    op.add_column('users', sa.Column('first_notebook_synced_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('first_ocr_completed_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('notion_connected_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('onboarding_dismissed', sa.Boolean(), nullable=False, server_default=sa.text('0')))
    op.add_column('users', sa.Column('drip_emails_sent', sa.String(255), nullable=False, server_default=''))


def downgrade() -> None:
    """Remove onboarding milestone tracking columns from users table."""
    op.drop_column('users', 'drip_emails_sent')
    op.drop_column('users', 'onboarding_dismissed')
    op.drop_column('users', 'notion_connected_at')
    op.drop_column('users', 'first_ocr_completed_at')
    op.drop_column('users', 'first_notebook_synced_at')
