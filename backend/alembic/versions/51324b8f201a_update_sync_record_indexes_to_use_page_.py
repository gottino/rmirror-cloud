"""update_sync_record_indexes_to_use_page_uuid

Revision ID: 51324b8f201a
Revises: d563f8a1feda
Create Date: 2025-12-30 21:22:58.108122

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '51324b8f201a'
down_revision: Union[str, Sequence[str], None] = 'd563f8a1feda'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Update sync_records indexes to use page_uuid as primary identifier."""
    connection = op.get_bind()

    # Log duplicate count for monitoring
    result = connection.execute(sa.text("""
        SELECT COUNT(*) as duplicate_count
        FROM sync_records
        WHERE page_uuid IS NOT NULL
        AND id NOT IN (
            SELECT MAX(id)
            FROM sync_records
            WHERE page_uuid IS NOT NULL
            GROUP BY page_uuid, target_name, user_id
        )
    """))
    duplicate_count = result.scalar()
    if duplicate_count > 0:
        print(f"⚠️  Cleaning up {duplicate_count} duplicate sync_records before applying unique constraint...")

    # Clean up duplicate records before applying unique constraint
    # Keep only the most recent record (highest id) for each (page_uuid, target_name, user_id)
    # This ensures we keep the latest sync state
    connection.execute(sa.text("""
        DELETE FROM sync_records
        WHERE page_uuid IS NOT NULL
        AND id NOT IN (
            SELECT MAX(id)
            FROM sync_records
            WHERE page_uuid IS NOT NULL
            GROUP BY page_uuid, target_name, user_id
        )
    """))

    if duplicate_count > 0:
        print(f"✅ Cleaned up {duplicate_count} duplicate records")

    # Drop old unique index on content_hash if it exists
    # Use IF EXISTS equivalent for production safety
    try:
        op.drop_index('idx_sync_content_target', table_name='sync_records')
    except Exception:
        # Index might not exist or already dropped, that's okay
        pass

    # Recreate as non-unique index
    # Check if it already exists first (for idempotency)
    inspector = sa.inspect(connection)
    existing_indexes = [idx['name'] for idx in inspector.get_indexes('sync_records')]
    if 'idx_sync_content_target' not in existing_indexes:
        op.create_index('idx_sync_content_target', 'sync_records', ['content_hash', 'target_name', 'user_id'])

    # Drop old page_uuid index if it exists
    try:
        op.drop_index('idx_sync_page_uuid', table_name='sync_records')
    except Exception:
        # Index might not exist or already dropped, that's okay
        pass

    # Create new unique index on page_uuid + target_name + user_id
    # Only if it doesn't already exist (for idempotency)
    if 'idx_sync_page_uuid' not in existing_indexes:
        op.create_index('idx_sync_page_uuid', 'sync_records', ['page_uuid', 'target_name', 'user_id'], unique=True)

    print("✅ Migration completed successfully")


def downgrade() -> None:
    """Revert sync_records indexes to use content_hash."""
    # Drop new unique page_uuid index
    op.drop_index('idx_sync_page_uuid', table_name='sync_records')

    # Recreate old page_uuid index
    op.create_index('idx_sync_page_uuid', 'sync_records', ['page_uuid'])

    # Drop non-unique content_hash index
    op.drop_index('idx_sync_content_target', table_name='sync_records')

    # Recreate as unique index
    op.create_index('idx_sync_content_target', 'sync_records', ['content_hash', 'target_name', 'user_id'], unique=True)
