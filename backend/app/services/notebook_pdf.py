"""Combined notebook PDF rebuilds, debounced via the background worker.

The combined notebook PDF is an eventually-consistent artifact (used for account
data export and deletion cleanup, never served on a latency-sensitive path). It
used to be rebuilt synchronously inside every single-page upload, which made a
full N-page sync O(N^2) in S3 round-trips. Now an upload only marks the notebook
dirty (``Notebook.pdf_dirty_at``); this module performs the actual rebuild once
the notebook has been quiet for a debounce window, collapsing a burst of N
uploads into a single rebuild.
"""

import logging
from datetime import datetime, timedelta
from io import BytesIO
from typing import Optional

from sqlalchemy.orm import Session

from app.core.pdf_service import PDFService
from app.models.notebook import Notebook
from app.models.notebook_page import NotebookPage
from app.models.page import Page
from app.storage import StorageService

logger = logging.getLogger(__name__)

# How long a notebook must be quiet (no new page uploads) before its combined
# PDF is rebuilt. A bursty initial sync pushes ``pdf_dirty_at`` forward on every
# page, so the rebuild fires once, this many seconds after the final page.
DEFAULT_PDF_REBUILD_DEBOUNCE_SECONDS = 60


async def rebuild_combined_pdf(
    db: Session, storage: StorageService, notebook: Notebook
) -> bool:
    """Download every page PDF for the notebook, combine them, and upload the result.

    Returns True if a combined PDF was rebuilt, or False if the notebook has no
    page PDFs to combine.
    """
    all_pages = (
        db.query(Page)
        .join(NotebookPage, NotebookPage.page_id == Page.id)
        .filter(
            NotebookPage.notebook_id == notebook.id,
            Page.pdf_s3_key.isnot(None),
        )
        .order_by(NotebookPage.page_number)
        .all()
    )

    if not all_pages:
        return False

    page_pdfs = []
    for p in all_pages:
        page_pdfs.append(await storage.download_file(p.pdf_s3_key))

    combined_pdf = PDFService.combine_page_pdfs(page_pdfs)

    notebook_pdf_key = (
        f"users/{notebook.user_id}/notebooks/{notebook.notebook_uuid}/notebook.pdf"
    )
    await storage.upload_file(
        BytesIO(combined_pdf), notebook_pdf_key, content_type="application/pdf"
    )

    notebook.notebook_pdf_s3_key = notebook_pdf_key
    db.commit()

    logger.info(
        "Rebuilt combined PDF for notebook %s (%d pages)", notebook.id, len(all_pages)
    )
    return True


async def rebuild_dirty_notebook_pdfs(
    db: Session,
    storage: StorageService,
    *,
    debounce_seconds: int = DEFAULT_PDF_REBUILD_DEBOUNCE_SECONDS,
    now: Optional[datetime] = None,
    limit: int = 20,
) -> int:
    """Rebuild combined PDFs for notebooks that have been dirty and quiet.

    A notebook is eligible when ``pdf_dirty_at`` is set and older than
    ``debounce_seconds`` (no new page arrived within the window). ``pdf_dirty_at``
    is cleared to NULL after processing so it is not reprocessed; this also clears
    the flag for the edge case of a dirty notebook with no page PDFs, preventing
    an endless re-sweep.

    Returns the number of notebooks whose combined PDF was actually rebuilt.
    """
    now = now or datetime.utcnow()
    cutoff = now - timedelta(seconds=debounce_seconds)

    dirty_notebooks = (
        db.query(Notebook)
        .filter(
            Notebook.pdf_dirty_at.isnot(None),
            Notebook.pdf_dirty_at <= cutoff,
        )
        .order_by(Notebook.pdf_dirty_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
        .all()
    )

    rebuilt = 0
    for notebook in dirty_notebooks:
        try:
            did_rebuild = await rebuild_combined_pdf(db, storage, notebook)
            notebook.pdf_dirty_at = None
            db.commit()
            if did_rebuild:
                rebuilt += 1
        except Exception:
            logger.error(
                "Failed to rebuild combined PDF for notebook %s",
                notebook.id,
                exc_info=True,
            )
            db.rollback()

    return rebuilt
