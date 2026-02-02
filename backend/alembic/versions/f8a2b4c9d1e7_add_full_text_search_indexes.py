"""add_full_text_search_indexes

Revision ID: f8a2b4c9d1e7
Revises: 330fb8f63d23
Create Date: 2026-02-02 21:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f8a2b4c9d1e7'
down_revision: Union[str, Sequence[str], None] = '330fb8f63d23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add pg_trgm extension and GIN indexes for fuzzy full-text search.

    PostgreSQL only - SQLite gracefully skips these operations.
    """
    connection = op.get_bind()

    if connection.dialect.name == 'postgresql':
        # Enable pg_trgm extension for trigram similarity matching
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        print("  Enabled pg_trgm extension")

        # Create GIN index on notebook names for fuzzy matching
        op.execute("""
            CREATE INDEX IF NOT EXISTS idx_notebooks_visible_name_trgm
            ON notebooks USING GIN (visible_name gin_trgm_ops)
        """)
        print("  Created GIN index on notebooks.visible_name")

        # Create GIN index on OCR text for fuzzy content search
        op.execute("""
            CREATE INDEX IF NOT EXISTS idx_pages_ocr_text_trgm
            ON pages USING GIN (ocr_text gin_trgm_ops)
        """)
        print("  Created GIN index on pages.ocr_text")

        print("Full-text search indexes created successfully")
    else:
        print("  Skipping pg_trgm indexes (SQLite does not support them)")
        print("  SQLite will use LIKE-based search as fallback")


def downgrade() -> None:
    """Remove full-text search indexes.

    Note: Does not remove pg_trgm extension as other features may use it.
    """
    connection = op.get_bind()

    if connection.dialect.name == 'postgresql':
        op.execute("DROP INDEX IF EXISTS idx_pages_ocr_text_trgm")
        op.execute("DROP INDEX IF EXISTS idx_notebooks_visible_name_trgm")
        print("  Removed full-text search GIN indexes")
        # Note: Not removing pg_trgm extension as it may be used elsewhere
    else:
        print("  No indexes to remove (SQLite)")
