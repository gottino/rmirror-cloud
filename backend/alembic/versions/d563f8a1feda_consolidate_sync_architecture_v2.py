"""consolidate_sync_architecture_v2

Implements unified sync architecture v2:
- Consolidates page_sync_records into sync_records
- Adds page tracking fields (notebook_uuid, page_number, page_uuid)
- Renames config_json to config_encrypted in integration_configs
- Adds fuzzy_signature and content_hash to todos table
- Creates sync_queue table for background processing

Revision ID: d563f8a1feda
Revises: 7a645000883a
Create Date: 2025-12-27 19:19:15.983233

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd563f8a1feda'
down_revision: Union[str, Sequence[str], None] = '7a645000883a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to sync architecture v2."""

    # Detect database type
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == 'sqlite'

    # 1. Add page tracking fields to sync_records
    op.add_column('sync_records', sa.Column('page_uuid', sa.String(length=255), nullable=True))
    op.add_column('sync_records', sa.Column('notebook_uuid', sa.String(length=255), nullable=True))
    op.add_column('sync_records', sa.Column('page_number', sa.Integer(), nullable=True))

    # Create indexes for new fields
    op.create_index('idx_sync_page_uuid', 'sync_records', ['page_uuid'], unique=False)
    op.create_index('idx_sync_notebook_page', 'sync_records', ['notebook_uuid', 'page_number'], unique=False)

    # 2. Migrate data from page_sync_records to sync_records
    # For each page_sync_record, create a corresponding sync_record with item_type='page_text'
    if is_sqlite:
        # SQLite version - use JSON function
        op.execute("""
            INSERT INTO sync_records (
                user_id, item_type, item_id, content_hash, page_uuid,
                notebook_uuid, page_number, target_name, external_id,
                status, error_message, retry_count, metadata_json,
                created_at, updated_at, synced_at
            )
            SELECT
                psr.user_id,
                'page_text' as item_type,
                CAST(np.page_id AS TEXT) as item_id,
                psr.content_hash,
                p.page_uuid,
                psr.notebook_uuid,
                psr.page_number,
                psr.target_name,
                COALESCE(psr.notion_page_id, psr.notion_block_id, '') as external_id,
                psr.status,
                psr.error_message,
                psr.retry_count,
                json_object(
                    'notion_page_id', psr.notion_page_id,
                    'notion_block_id', psr.notion_block_id
                ) as metadata_json,
                psr.created_at,
                psr.updated_at,
                psr.synced_at
            FROM page_sync_records psr
            LEFT JOIN notebook_pages np ON (
                psr.notebook_uuid = (SELECT notebook_uuid FROM notebooks WHERE id = (SELECT notebook_id FROM pages WHERE id = np.page_id LIMIT 1))
                AND psr.page_number = np.page_number
            )
            LEFT JOIN pages p ON p.id = np.page_id
            WHERE NOT EXISTS (
                SELECT 1 FROM sync_records sr
                WHERE sr.content_hash = psr.content_hash
                AND sr.target_name = psr.target_name
                AND sr.user_id = psr.user_id
            )
        """)
    else:
        # PostgreSQL version
        op.execute("""
            INSERT INTO sync_records (
                user_id, item_type, item_id, content_hash, page_uuid,
                notebook_uuid, page_number, target_name, external_id,
                status, error_message, retry_count, metadata_json,
                created_at, updated_at, synced_at
            )
            SELECT
                psr.user_id,
                'page_text' as item_type,
                CAST(np.page_id AS VARCHAR) as item_id,
                psr.content_hash,
                p.page_uuid,
                psr.notebook_uuid,
                psr.page_number,
                psr.target_name,
                COALESCE(psr.notion_page_id, psr.notion_block_id, '') as external_id,
                psr.status,
                psr.error_message,
                psr.retry_count,
                json_build_object(
                    'notion_page_id', psr.notion_page_id,
                    'notion_block_id', psr.notion_block_id
                )::text as metadata_json,
                psr.created_at,
                psr.updated_at,
                psr.synced_at
            FROM page_sync_records psr
            LEFT JOIN notebook_pages np ON (
                psr.notebook_uuid = (SELECT notebook_uuid FROM notebooks WHERE id = (SELECT notebook_id FROM pages WHERE id = np.page_id LIMIT 1))
                AND psr.page_number = np.page_number
            )
            LEFT JOIN pages p ON p.id = np.page_id
            WHERE NOT EXISTS (
                SELECT 1 FROM sync_records sr
                WHERE sr.content_hash = psr.content_hash
                AND sr.target_name = psr.target_name
                AND sr.user_id = psr.user_id
            )
        """)

    # 3. Drop page_sync_records table (data migrated)
    op.drop_table('page_sync_records')

    # 4. Rename config_json to config_encrypted in integration_configs
    op.alter_column('integration_configs', 'config_json',
                    new_column_name='config_encrypted',
                    existing_type=sa.Text(),
                    existing_nullable=False)

    # 5. Add fuzzy deduplication fields to todos table
    op.add_column('todos', sa.Column('content_hash', sa.String(length=64), nullable=True))
    op.add_column('todos', sa.Column('fuzzy_signature', sa.String(length=100), nullable=True))

    # Create unique constraint for fuzzy deduplication
    # Note: This will fail if there are existing duplicate todos - that's intentional
    # Users should clean duplicates before running migration
    op.create_index('idx_todos_fuzzy', 'todos', ['fuzzy_signature', 'notebook_id', 'user_id'], unique=True)

    # 6. Create sync_queue table for background processing
    op.create_table(
        'sync_queue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),

        # Item to sync
        sa.Column('item_type', sa.String(length=50), nullable=False),  # 'page_text', 'todo', 'highlight'
        sa.Column('item_id', sa.String(length=255), nullable=False),   # Source item ID
        sa.Column('content_hash', sa.String(length=64), nullable=False),

        # Context
        sa.Column('page_uuid', sa.String(length=255), nullable=True),
        sa.Column('notebook_uuid', sa.String(length=255), nullable=True),
        sa.Column('page_number', sa.Integer(), nullable=True),

        # Target
        sa.Column('target_name', sa.String(length=50), nullable=False),

        # Queue status
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),  # pending, processing, completed, failed
        sa.Column('priority', sa.Integer(), nullable=False, server_default='5'),  # 1-10, lower = higher priority
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('metadata_json', sa.Text(), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('scheduled_at', sa.DateTime(), nullable=True),  # For retry backoff
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),

        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for sync_queue
    op.create_index('idx_queue_user', 'sync_queue', ['user_id'], unique=False)
    op.create_index('idx_queue_status', 'sync_queue', ['status'], unique=False)
    op.create_index('idx_queue_target', 'sync_queue', ['target_name'], unique=False)
    op.create_index('idx_queue_scheduled', 'sync_queue', ['scheduled_at'], unique=False)
    op.create_index('idx_queue_priority_status', 'sync_queue', ['priority', 'status', 'scheduled_at'], unique=False)

    # Prevent duplicate queue entries
    op.create_index('idx_queue_dedup', 'sync_queue', ['content_hash', 'target_name', 'user_id', 'status'], unique=False)


def downgrade() -> None:
    """Downgrade schema from sync architecture v2."""

    # Drop sync_queue
    op.drop_table('sync_queue')

    # Remove fuzzy deduplication from todos
    op.drop_index('idx_todos_fuzzy', table_name='todos')
    op.drop_column('todos', 'fuzzy_signature')
    op.drop_column('todos', 'content_hash')

    # Rename config_encrypted back to config_json
    op.alter_column('integration_configs', 'config_encrypted',
                    new_column_name='config_json',
                    existing_type=sa.Text(),
                    existing_nullable=False)

    # Recreate page_sync_records table
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

    # Restore indexes
    op.create_index('idx_page_sync_notebook_page_target', 'page_sync_records',
                   ['notebook_uuid', 'page_number', 'target_name', 'user_id'], unique=True)
    op.create_index(op.f('ix_page_sync_records_content_hash'), 'page_sync_records', ['content_hash'], unique=False)
    op.create_index(op.f('ix_page_sync_records_notebook_uuid'), 'page_sync_records', ['notebook_uuid'], unique=False)
    op.create_index(op.f('ix_page_sync_records_notion_block_id'), 'page_sync_records', ['notion_block_id'], unique=False)
    op.create_index(op.f('ix_page_sync_records_notion_page_id'), 'page_sync_records', ['notion_page_id'], unique=False)
    op.create_index(op.f('ix_page_sync_records_status'), 'page_sync_records', ['status'], unique=False)
    op.create_index(op.f('ix_page_sync_records_target_name'), 'page_sync_records', ['target_name'], unique=False)
    op.create_index(op.f('ix_page_sync_records_user_id'), 'page_sync_records', ['user_id'], unique=False)

    # Migrate data back from sync_records to page_sync_records
    op.execute("""
        INSERT INTO page_sync_records (
            user_id, notebook_uuid, page_number, content_hash, target_name,
            notion_page_id, notion_block_id, status, error_message, retry_count,
            created_at, updated_at, synced_at
        )
        SELECT
            sr.user_id,
            sr.notebook_uuid,
            sr.page_number,
            sr.content_hash,
            sr.target_name,
            (sr.metadata_json::json->>'notion_page_id')::varchar as notion_page_id,
            (sr.metadata_json::json->>'notion_block_id')::varchar as notion_block_id,
            sr.status,
            sr.error_message,
            sr.retry_count,
            sr.created_at,
            sr.updated_at,
            sr.synced_at
        FROM sync_records sr
        WHERE sr.item_type = 'page_text'
        AND sr.notebook_uuid IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM page_sync_records psr
            WHERE psr.notebook_uuid = sr.notebook_uuid
            AND psr.page_number = sr.page_number
            AND psr.target_name = sr.target_name
            AND psr.user_id = sr.user_id
        )
    """)

    # Remove page tracking fields from sync_records
    op.drop_index('idx_sync_notebook_page', table_name='sync_records')
    op.drop_index('idx_sync_page_uuid', table_name='sync_records')
    op.drop_column('sync_records', 'page_number')
    op.drop_column('sync_records', 'notebook_uuid')
    op.drop_column('sync_records', 'page_uuid')
