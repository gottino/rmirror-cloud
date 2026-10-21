"""Combined notebook PDF rebuilds, debounced via the background worker.

The combined notebook PDF is an eventually-consistent artifact (counted in the
account data summary and removed on deletion; nothing serves it to users). It
used to be rebuilt synchronously inside every single-page upload, which made a
full N-page sync O(N^2) in S3 round-trips. Now an upload only marks the notebook
dirty (``Notebook.pdf_dirty_at``); this module performs the actual rebuild once
the notebook has been quiet for a debounce window, collapsing a burst of N
uploads into a single rebuild.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from io import BytesIO
from typing import List, Optional

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

# A sweep claims a notebook by moving ``pdf_dirty_at`` this far into the future,
# so other workers skip it while it rebuilds. If the rebuild fails the claim is
# simply left to expire, which doubles as the retry backoff.
PDF_REBUILD_CLAIM_SECONDS = 600


def _page_pdf_keys(db: Session, notebook_id: int) -> List[str]:
    """Storage keys of the notebook's page PDFs, in page order."""
    rows = (
        db.query(Page.pdf_s3_key)
        .join(NotebookPage, NotebookPage.page_id == Page.id)
        .filter(
            NotebookPage.notebook_id == notebook_id,
            Page.pdf_s3_key.isnot(None),
        )
        .order_by(NotebookPage.page_number)
        .all()
    )
    return [key for (key,) in rows]


def _combined_pdf_key(notebook: Notebook) -> str:
    return f"users/{notebook.user_id}/notebooks/{notebook.notebook_uuid}/notebook.pdf"


async def _build_and_upload(storage: StorageService, page_keys: List[str], dest_key: str) -> int:
    """Download the page PDFs, combine them and upload the result.

    Returns the number of pages combined. A page whose PDF is missing from
    storage is skipped rather than failing the whole notebook, which would
    otherwise retry forever.
    """
    page_pdfs = []
    for key in page_keys:
        try:
            page_pdfs.append(await storage.download_file(key))
        except FileNotFoundError:
            logger.warning("Page PDF %s missing from storage; leaving it out", key)
    if not page_pdfs:
        return 0

    combined_pdf = PDFService.combine_page_pdfs(page_pdfs)
    await storage.upload_file(BytesIO(combined_pdf), dest_key, content_type="application/pdf")
    return len(page_pdfs)


async def _build_and_upload_off_loop(
    storage: StorageService, page_keys: List[str], dest_key: str
) -> int:
    """Run _build_and_upload in a worker thread.

    The storage client is blocking boto3 behind async methods and the combine
    is CPU-bound; inside the API process's event loop either would stall
    request handling for the whole rebuild.
    """
    return await asyncio.to_thread(asyncio.run, _build_and_upload(storage, page_keys, dest_key))


async def rebuild_combined_pdf(
    db: Session, storage: StorageService, notebook: Notebook
) -> bool:
    """Download every page PDF for the notebook, combine them, and upload the result.

    Returns True if a combined PDF was rebuilt, or False if the notebook has no
    page PDFs to combine.
    """
    page_keys = _page_pdf_keys(db, notebook.id)
    if not page_keys:
        return False

    dest_key = _combined_pdf_key(notebook)
    pages = await _build_and_upload_off_loop(storage, page_keys, dest_key)
    if not pages:
        return False

    notebook.notebook_pdf_s3_key = dest_key
    db.commit()

    logger.info("Rebuilt combined PDF for notebook %s (%d pages)", notebook.id, pages)
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
    ``debounce_seconds`` (no new page arrived within the window). Each notebook
    is claimed with a conditional update before any storage work, so concurrent
    workers never rebuild the same notebook, and ``pdf_dirty_at`` is cleared
    afterwards only if it still holds the claim: a page uploaded during the
    rebuild overwrites it, and the notebook is rebuilt again on a later sweep.

    Returns the number of notebooks whose combined PDF was actually rebuilt.
    """
    now = now or datetime.utcnow()
    cutoff = now - timedelta(seconds=debounce_seconds)

    candidates = (
        db.query(Notebook.id, Notebook.pdf_dirty_at)
        .filter(
            Notebook.pdf_dirty_at.isnot(None),
            Notebook.pdf_dirty_at <= cutoff,
        )
        .order_by(Notebook.pdf_dirty_at.asc())
        .limit(limit)
        .all()
    )

    rebuilt = 0
    for notebook_id, observed_dirty_at in candidates:
        claim = now + timedelta(seconds=PDF_REBUILD_CLAIM_SECONDS)
        claimed = (
            db.query(Notebook)
            .filter(Notebook.id == notebook_id, Notebook.pdf_dirty_at == observed_dirty_at)
            .update({Notebook.pdf_dirty_at: claim}, synchronize_session=False)
        )
        db.commit()
        if not claimed:
            continue  # another worker claimed it, or a page arrived since the query

        try:
            notebook = db.get(Notebook, notebook_id)
            if notebook is None:
                continue
            page_keys = _page_pdf_keys(db, notebook_id)
            dest_key = _combined_pdf_key(notebook)

            pages = 0
            if page_keys:
                pages = await _build_and_upload_off_loop(storage, page_keys, dest_key)

            if pages:
                stored = (
                    db.query(Notebook)
                    .filter(Notebook.id == notebook_id)
                    .update({Notebook.notebook_pdf_s3_key: dest_key}, synchronize_session=False)
                )
                if not stored:
                    # Deleted while we rebuilt: its cleanup couldn't know about
                    # this upload, so remove it here rather than orphan it.
                    db.commit()
                    await storage.delete_file(dest_key)
                    continue

            # Clear the flag only if no page arrived since the claim
            db.query(Notebook).filter(
                Notebook.id == notebook_id, Notebook.pdf_dirty_at == claim
            ).update({Notebook.pdf_dirty_at: None}, synchronize_session=False)
            db.commit()
            if pages:
                rebuilt += 1
                logger.info(
                    "Rebuilt combined PDF for notebook %s (%d pages)", notebook_id, pages
                )
        except Exception:
            logger.error(
                "Failed to rebuild combined PDF for notebook %s; retrying after %ss",
                notebook_id,
                PDF_REBUILD_CLAIM_SECONDS,
                exc_info=True,
            )
            db.rollback()

    return rebuilt
