"""rename_config_json_to_config_encrypted

Revision ID: 5ae75127c19e
Revises: 51324b8f201a
Create Date: 2025-12-30 21:52:07.389088

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '5ae75127c19e'
down_revision: Union[str, Sequence[str], None] = '51324b8f201a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename config_json to config_encrypted in integration_configs table."""
    connection = op.get_bind()
    inspector = sa.inspect(connection)

    # Get current column names
    columns = [col['name'] for col in inspector.get_columns('integration_configs')]

    # Only rename if config_json exists and config_encrypted doesn't
    if 'config_json' in columns and 'config_encrypted' not in columns:
        op.alter_column('integration_configs', 'config_json',
                        new_column_name='config_encrypted')
        print("✓ Renamed config_json to config_encrypted")
    elif 'config_encrypted' in columns:
        print("✓ Column already renamed to config_encrypted")
    else:
        print("⚠️ Neither config_json nor config_encrypted found")


def downgrade() -> None:
    """Revert config_encrypted back to config_json."""
    op.alter_column('integration_configs', 'config_encrypted',
                    new_column_name='config_json')
