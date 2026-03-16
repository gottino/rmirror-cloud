"""backfill obsidian content hashes

Revision ID: 30f649af594a
Revises: e5e8f0fad035
Create Date: 2026-03-16 19:36:54.727284

"""
import hashlib
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '30f649af594a'
down_revision: Union[str, Sequence[str], None] = 'e5e8f0fad035'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def compute_hash(pages: list[tuple[int, str]]) -> str | None:
    """Compute content hash from (page_number, ocr_text) tuples."""
    if not pages:
        return None
    hash_input = "".join(f"{pn}:{text}" for pn, text in pages)
    return hashlib.sha256(hash_input.encode()).hexdigest()


def upgrade() -> None:
    """Backfill obsidian_content_hash for notebooks with completed OCR pages."""
    conn = op.get_bind()

    # Find notebooks missing the hash
    notebooks = conn.execute(
        sa.text("""
            SELECT n.id, n.notebook_uuid
            FROM notebooks n
            WHERE n.obsidian_content_hash IS NULL
              AND n.deleted = false
        """)
    ).fetchall()

    for nb_id, nb_uuid in notebooks:
        # Get completed OCR pages for this notebook
        pages = conn.execute(
            sa.text("""
                SELECT np.page_number, p.ocr_text
                FROM notebook_pages np
                JOIN pages p ON np.page_id = p.id
                WHERE np.notebook_id = :nb_id
                  AND p.ocr_status = 'completed'
                ORDER BY np.page_number
            """),
            {"nb_id": nb_id},
        ).fetchall()

        content_hash = compute_hash([(pn, text or "") for pn, text in pages])
        if content_hash:
            conn.execute(
                sa.text("""
                    UPDATE notebooks
                    SET obsidian_content_hash = :hash
                    WHERE id = :nb_id
                """),
                {"hash": content_hash, "nb_id": nb_id},
            )


def downgrade() -> None:
    """No-op: cannot un-backfill reliably."""
    pass
