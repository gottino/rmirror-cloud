"""Background job to process pending OCR pages when quota resets."""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.ocr_service import OCRService
from app.dependencies import get_storage_service
from app.models.notebook import Notebook
from app.models.page import OcrStatus, Page
from app.services import quota_service

logger = logging.getLogger(__name__)


async def process_pending_pages_for_user(db: Session, user_id: int) -> int:
    """
    Process all PENDING_QUOTA pages for a user.

    Called when quota resets or user upgrades to Pro tier.

    IMPORTANT: Processes NEWEST pages first (created_at DESC), so if user has
    more pending pages than quota allows (e.g., 50 pending, 30 quota), they get
    their most recent work OCR'd first, not their oldest pages.

    Args:
        db: Database session
        user_id: User ID to process pending pages for

    Returns:
        Number of pages successfully processed

    Example:
        >>> # User has 50 pending pages, quota resets to 0/30
        >>> count = await process_pending_pages_for_user(db, user_id=42)
        >>> # Result: 30 newest pages processed, 20 oldest still pending
    """
    # Get all PENDING_QUOTA pages for user, ordered newest first
    pending_pages = (
        db.query(Page)
        .join(Notebook, Notebook.id == Page.notebook_id)
        .filter(
            Notebook.user_id == user_id,
            Page.ocr_status == OcrStatus.PENDING_QUOTA,
            Page.pdf_s3_key.isnot(None),  # Must have PDF to process
        )
        .order_by(Page.created_at.desc())  # DESC = newest first!
        .all()
    )

    if not pending_pages:
        logger.info(f"No pending pages to process for user {user_id}")
        return 0

    logger.info(
        f"Found {len(pending_pages)} pending pages for user {user_id}, "
        f"processing newest first..."
    )

    ocr_service = OCRService()
    storage = get_storage_service()
    processed_count = 0
    failed_count = 0

    for page in pending_pages:
        # Check quota before each page (stop if exhausted)
        if not quota_service.check_quota(db, user_id):
            logger.info(
                f"Quota exhausted after processing {processed_count} pages for user {user_id}. "
                f"Remaining {len(pending_pages) - processed_count} pages still pending."
            )
            break

        try:
            # Download PDF from storage
            logger.debug(f"Downloading PDF for page {page.id}: {page.pdf_s3_key}")
            pdf_bytes = await storage.download_file(page.pdf_s3_key)

            # Run OCR
            logger.debug(f"Running OCR for page {page.id}")
            ocr_text = await ocr_service.extract_text_from_pdf(pdf_bytes)

            # Update page
            page.ocr_text = ocr_text
            page.ocr_status = OcrStatus.COMPLETED
            page.ocr_completed_at = datetime.utcnow()

            # Consume quota
            quota_service.consume_quota(db, user_id, amount=1)
            processed_count += 1

            logger.info(
                f"Processed pending page {page.id} for user {user_id} "
                f"({processed_count}/{len(pending_pages)})"
            )

            db.commit()

        except quota_service.QuotaExceededError:
            # Quota exhausted during processing (race condition)
            logger.warning(
                f"Quota exhausted while processing page {page.id} for user {user_id}"
            )
            db.rollback()
            break

        except Exception as e:
            logger.error(
                f"Failed to process pending page {page.id} for user {user_id}: {e}",
                exc_info=True,
            )
            # Mark as failed but continue processing other pages
            page.ocr_status = OcrStatus.FAILED
            page.ocr_error = str(e)[:500]  # Limit error message length
            failed_count += 1

            try:
                db.commit()
            except Exception as commit_error:
                logger.error(f"Failed to commit error status: {commit_error}")
                db.rollback()

    logger.info(
        f"Retroactive processing complete for user {user_id}: "
        f"{processed_count} processed, {failed_count} failed, "
        f"{len(pending_pages) - processed_count - failed_count} still pending"
    )

    return processed_count
