"""page ocr attempts

Revision ID: d7a3f9c2e5b1
Revises: c3d8e1f2a4b6
Create Date: 2026-11-22

A failed OCR call (provider error, timeout, network) no longer fails the
upload: the page is stored as ``pending_retry`` and the sync worker retries it
with backoff. ``ocr_attempts`` counts the failed calls for the page's current
content so the retries stop after a bound. Existing rows start at 0.
(``ocr_status`` is a plain string column, so the new status needs no DDL.)
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7a3f9c2e5b1"
down_revision: Union[str, Sequence[str], None] = "c3d8e1f2a4b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pages",
        sa.Column("ocr_attempts", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("pages", "ocr_attempts")
