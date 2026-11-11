"""What happens after a page's OCR finishes, shared by every OCR path.

Both the upload endpoint (``app/api/processing.py``) and the retroactive OCR of
``PENDING_QUOTA`` pages (``app/jobs/process_pending_pages.py``) call
``on_ocr_completed`` so a page reaches Obsidian and the push integrations
(Notion, ...) the same way however it was OCR'd.
"""

import logging

from sqlalchemy.orm import Session

from app.models.notebook import Notebook
from app.models.notebook_page import NotebookPage
from app.models.page import OcrStatus, Page
from app.models.sync_record import IntegrationConfig
from app.services.fingerprinting import fingerprint_page
from app.services.obsidian_service import compute_notebook_content_hash
from app.services.sync_queue import queue_sync

logger = logging.getLogger(__name__)


def update_obsidian_content_hash(db: Session, notebook: Notebook) -> None:
    """Recompute the notebook's Obsidian content hash (pull-based sync). Non-fatal."""
    try:
        ocr_pages = (
            db.query(NotebookPage.page_number, Page.ocr_text)
            .join(Page, NotebookPage.page_id == Page.id)
            .filter(
                NotebookPage.notebook_id == notebook.id,
                Page.ocr_status == OcrStatus.COMPLETED.value,
                Page.ocr_text.isnot(None),
            )
            .order_by(NotebookPage.page_number)
            .all()
        )

        notebook.obsidian_content_hash = compute_notebook_content_hash(
            [(pn, text) for pn, text in ocr_pages]
        )
        db.commit()
    except Exception as e:
        logger.error(f"Failed to update obsidian content hash: {e}")
        db.rollback()


def enqueue_integration_syncs(db: Session, page: Page, notebook: Notebook) -> int:
    """Queue the page's OCR text for every enabled push integration.

    Obsidian is skipped: it pulls via its own endpoints (content hash above).
    Queueing failures are logged and never raised.

    Returns:
        Number of integrations the page was queued for.
    """
    notebook_page = (
        db.query(NotebookPage)
        .filter(
            NotebookPage.notebook_id == notebook.id,
            NotebookPage.page_id == page.id,
        )
        .first()
    )
    page_number = notebook_page.page_number if notebook_page else None

    active_integrations = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.user_id == notebook.user_id,
            IntegrationConfig.is_enabled == True,  # noqa: E712
        )
        .all()
    )

    logger.info(
        f"Found {len(active_integrations)} active integrations for user {notebook.user_id}"
    )

    queued = 0
    for integration in active_integrations:
        if integration.target_name == "obsidian":
            continue

        try:
            content_hash = fingerprint_page(
                notebook_uuid=notebook.notebook_uuid,
                page_number=page_number or 0,
                ocr_text=page.ocr_text,
                page_uuid=page.page_uuid,
            )

            queue_entry = queue_sync(
                db=db,
                user_id=notebook.user_id,
                item_type="page_text",
                item_id=str(page.id),
                content_hash=content_hash,
                target_name=integration.target_name,
                page_uuid=page.page_uuid,
                notebook_uuid=notebook.notebook_uuid,
                page_number=page_number,
                metadata={
                    "notebook_name": notebook.visible_name,
                    "notebook_id": notebook.id,
                    "page_id": page.id,
                },
            )
            queued += 1

            logger.info(
                f"Queued sync to {integration.target_name}: "
                f"queue_id={queue_entry.id}, status={queue_entry.status}"
            )
        except Exception as e:
            logger.error(f"Failed to queue sync to {integration.target_name}: {e}")
            db.rollback()

    db.commit()
    return queued


def on_ocr_completed(db: Session, page: Page, notebook: Notebook) -> None:
    """Run the follow-up work for a page whose OCR just finished.

    The page must already be committed with its OCR result. This updates the
    notebook's Obsidian content hash and, when OCR produced text, queues the
    page for the user's push integrations. Queueing depends only on OCR having
    completed with text, not on quota left afterwards: integration syncs do not
    consume OCR quota, and the page that used the last unit must sync too.
    (Pages that were not OCR'd because the quota ran out have no text and are
    never queued here.)
    """
    update_obsidian_content_hash(db, notebook)

    if page.ocr_status == OcrStatus.COMPLETED and page.ocr_text:
        enqueue_integration_syncs(db, page, notebook)
