"""add unified sync tables and integration configs

Revision ID: 25dbfc9e1b86
Revises: d9e72c9e7ed9
Create Date: 2025-11-13 22:36:28.066915

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '25dbfc9e1b86'
down_revision: Union[str, Sequence[str], None] = 'd9e72c9e7ed9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop old sync_records table if it exists (old schema)
    op.execute("DROP TABLE IF EXISTS sync_records")

    # Create new unified sync_records table
    op.create_table(
        'sync_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('target_name', sa.String(length=50), nullable=False),
        sa.Column('external_id', sa.String(length=500), nullable=False),
        sa.Column('item_type', sa.String(length=50), nullable=False),
        sa.Column('item_id', sa.String(length=500), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('synced_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for sync_records
    op.create_index('idx_sync_content_target', 'sync_records', ['content_hash', 'target_name', 'user_id'], unique=True)
    op.create_index('idx_sync_content_target_item', 'sync_records', ['content_hash', 'target_name', 'item_id'], unique=False)
    op.create_index(op.f('ix_sync_records_content_hash'), 'sync_records', ['content_hash'], unique=False)
    op.create_index(op.f('ix_sync_records_item_id'), 'sync_records', ['item_id'], unique=False)
    op.create_index(op.f('ix_sync_records_status'), 'sync_records', ['status'], unique=False)
    op.create_index(op.f('ix_sync_records_target_name'), 'sync_records', ['target_name'], unique=False)
    op.create_index(op.f('ix_sync_records_user_id'), 'sync_records', ['user_id'], unique=False)

    # Create page_sync_records table
    op.create_table(
        'page_sync_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('notebook_uuid', sa.String(length=255), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('target_name', sa.String(length=50), nullable=False),
        sa.Column('notion_page_id', sa.String(length=500), nullable=True),
        sa.Column('notion_block_id', sa.String(length=500), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('synced_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for page_sync_records
    op.create_index('idx_page_sync_notebook_page_target', 'page_sync_records', ['notebook_uuid', 'page_number', 'target_name', 'user_id'], unique=True)
    op.create_index(op.f('ix_page_sync_records_content_hash'), 'page_sync_records', ['content_hash'], unique=False)
    op.create_index(op.f('ix_page_sync_records_notebook_uuid'), 'page_sync_records', ['notebook_uuid'], unique=False)
    op.create_index(op.f('ix_page_sync_records_notion_block_id'), 'page_sync_records', ['notion_block_id'], unique=False)
    op.create_index(op.f('ix_page_sync_records_notion_page_id'), 'page_sync_records', ['notion_page_id'], unique=False)
    op.create_index(op.f('ix_page_sync_records_status'), 'page_sync_records', ['status'], unique=False)
    op.create_index(op.f('ix_page_sync_records_target_name'), 'page_sync_records', ['target_name'], unique=False)
    op.create_index(op.f('ix_page_sync_records_user_id'), 'page_sync_records', ['user_id'], unique=False)

    # Create integration_configs table
    op.create_table(
        'integration_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('target_name', sa.String(length=50), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('config_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for integration_configs
    op.create_index('idx_integration_user_target', 'integration_configs', ['user_id', 'target_name'], unique=True)
    op.create_index(op.f('ix_integration_configs_target_name'), 'integration_configs', ['target_name'], unique=False)
    op.create_index(op.f('ix_integration_configs_user_id'), 'integration_configs', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop all created tables and indexes
    op.drop_table('integration_configs')
    op.drop_table('page_sync_records')
    op.drop_table('sync_records')
