"""add_obsidian_sync_fields

Revision ID: e5e8f0fad035
Revises: a1b2c3d4e5f6
Create Date: 2026-03-15 22:40:27.965060

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5e8f0fad035'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "integration_configs",
        sa.Column("api_key_hash", sa.String(64), nullable=True),
    )
    op.create_index("ix_integration_configs_api_key_hash", "integration_configs", ["api_key_hash"])

    op.add_column(
        "notebooks",
        sa.Column("obsidian_content_hash", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("notebooks", "obsidian_content_hash")
    op.drop_index("ix_integration_configs_api_key_hash", table_name="integration_configs")
    op.drop_column("integration_configs", "api_key_hash")
