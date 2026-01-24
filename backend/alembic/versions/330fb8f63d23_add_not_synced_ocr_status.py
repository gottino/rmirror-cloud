"""add_not_synced_ocr_status

Add 'not_synced' OCR status for metadata-first sync architecture.

This status indicates that a page has been registered during metadata sync
but the actual content (.rm file) has not yet been uploaded. This allows
the dashboard to show all pages immediately during onboarding, with clear
visual distinction between synced and not-yet-synced pages.

New status value: 'not_synced'
- Used when: Metadata sync creates page stubs before content upload
- Transitions to: 'pending' when content is uploaded, then 'completed' after OCR

Revision ID: 330fb8f63d23
Revises: 2d86de0d1c3c
Create Date: 2026-01-12 12:41:50.269108

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '330fb8f63d23'
down_revision: Union[str, Sequence[str], None] = '2d86de0d1c3c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    The ocr_status column uses VARCHAR(20), not a PostgreSQL ENUM type,
    so no DDL change is needed to add the new status value.

    This migration updates any existing orphan pages (pages with no content
    uploaded yet) from 'pending' to 'not_synced' for consistency.
    """
    # Update any existing orphan pages (no s3_key means content not uploaded)
    # to use the new 'not_synced' status
    op.execute("""
        UPDATE pages
        SET ocr_status = 'not_synced'
        WHERE s3_key IS NULL
          AND ocr_status = 'pending'
    """)


def downgrade() -> None:
    """Downgrade schema.

    Revert 'not_synced' pages back to 'pending' status.
    """
    op.execute("""
        UPDATE pages
        SET ocr_status = 'pending'
        WHERE ocr_status = 'not_synced'
    """)
