"""Background job to process pending OCR pages when quota resets.

Pages uploaded while a user's OCR quota is exhausted are stored with
``OcrStatus.PENDING_QUOTA``. Once the quota has room again (a period reset or
an upgrade), the background sync worker calls ``process_pending_quota_pages``
each poll; it picks a few eligible users and OCRs a bounded number of their
pending pages, newest first.

Pages whose OCR call failed (provider error, timeout, network) are stored as
``OcrStatus.PENDING_RETRY`` and go through the same sweep once their backoff
has passed (``retry_due``). After ``MAX_OCR_ATTEMPTS`` failed calls a page is
marked ``FAILED``; re-uploading it (the upload endpoint re-OCRs FAILED pages)
starts over.
"""

import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Iterator, Optional

from sqlalchemy import and_, or_, text
from sqlalchemy.orm import Session

from app.core.ocr_service import OCRService
from app.dependencies import get_storage_service
from app.models.notebook import Notebook
from app.models.page import OcrStatus, Page
from app.models.quota_usage import QuotaType, QuotaUsage
from app.services import quota_service
from app.services.page_events import on_ocr_completed

logger = logging.getLogger(__name__)

# Per-poll work limits for the sync worker, so a user with thousands of pending
# pages can't hold up the sync queue: each poll handles at most
# MAX_USERS_PER_POLL users and MAX_PAGES_PER_USER pages for each of them.
MAX_USERS_PER_POLL = 2
MAX_PAGES_PER_USER = 5

# First key of the two-key Postgres advisory lock taken per user (second key is
# the user id). Arbitrary constant ("RQOC"), just distinct from other locks.
PENDING_QUOTA_LOCK_CLASS = 0x52514F43

# Failed OCR calls a page may accumulate (the upload's own attempt included)
# before it is marked FAILED. Retry n waits OCR_RETRY_BASE_DELAY * 2**(n-1)
# after the previous failure: 15 min, 30 min, ... 16 h; about 32 h in all, so a
# provider outage or an exhausted API key that is fixed within a day recovers
# without the user re-uploading, and a broken key costs at most a few calls
# per page.
MAX_OCR_ATTEMPTS = 8
OCR_RETRY_BASE_DELAY = timedelta(minutes=15)

# What the page (and so the dashboard) shows; never the provider's own text.
OCR_RETRY_MESSAGE = "OCR is temporarily unavailable; it will be retried automatically."
OCR_GAVE_UP_MESSAGE = "OCR failed after several attempts. Upload the page again to retry."


def ocr_retry_delay(attempts: int) -> timedelta:
    """Wait before the next OCR call for a page that has failed ``attempts`` times."""
    return OCR_RETRY_BASE_DELAY * (2 ** max(attempts - 1, 0))


def record_ocr_failure(page: Page) -> bool:
    """Count a failed OCR call on ``page`` and set its status (caller commits).

    Returns True if the page will be retried (PENDING_RETRY), False if it has
    used up ``MAX_OCR_ATTEMPTS`` and is now FAILED. The stored error is a
    generic message: provider errors are logged by the caller, never stored.
    """
    page.ocr_attempts = (page.ocr_attempts or 0) + 1
    page.ocr_text = None
    page.ocr_completed_at = None
    if page.ocr_attempts >= MAX_OCR_ATTEMPTS:
        page.ocr_status = OcrStatus.FAILED
        page.ocr_error = OCR_GAVE_UP_MESSAGE
        return False
    page.ocr_status = OcrStatus.PENDING_RETRY
    page.ocr_error = OCR_RETRY_MESSAGE
    return True


def retry_due(now: datetime):
    """SQL filter: PENDING_RETRY pages whose backoff has passed.

    ``updated_at`` is the time of the last failed call (the failure is the last
    write to the row). Written as one branch per attempt count so it is plain,
    portable SQL.
    """
    return and_(
        Page.ocr_status == OcrStatus.PENDING_RETRY,
        or_(
            *(
                and_(Page.ocr_attempts == n, Page.updated_at <= now - ocr_retry_delay(n))
                for n in range(0, MAX_OCR_ATTEMPTS)
            )
        ),
    )


def _processable(now: datetime):
    """SQL filter: pages the sweep may OCR now (PENDING_QUOTA, or a due retry)."""
    return and_(
        or_(Page.ocr_status == OcrStatus.PENDING_QUOTA, retry_due(now)),
        Page.pdf_s3_key.isnot(None),  # Must have PDF to process
    )


async def process_pending_pages_for_user(
    db: Session, user_id: int, limit: Optional[int] = None
) -> int:
    """
    Process all PENDING_QUOTA pages (and PENDING_RETRY pages that are due) for a user.

    Called when quota resets or user upgrades to Pro tier.

    IMPORTANT: Processes NEWEST pages first (created_at DESC), so if user has
    more pending pages than quota allows (e.g., 50 pending, 30 quota), they get
    their most recent work OCR'd first, not their oldest pages.

    One unit of quota is reserved atomically before each page's OCR and given
    back if OCR fails or finds no text; processing stops as soon as a
    reservation is refused. Each OCR'd page then goes through
    ``on_ocr_completed`` (Obsidian hash, integration syncs), like an upload.
    A failed OCR call is recorded with ``record_ocr_failure`` (retry with
    backoff, FAILED after ``MAX_OCR_ATTEMPTS``) and ends this user's batch:
    when the provider is down, the next pages would fail the same way.

    Callers that can run concurrently (the sync worker in each uvicorn process)
    must hold the user's claim (``_user_claim``) while calling this.

    Args:
        db: Database session
        user_id: User ID to process pending pages for
        limit: Process at most this many pages (newest first); None = all

    Returns:
        Number of pages successfully processed

    Example:
        >>> # User has 50 pending pages, quota resets to 0/30
        >>> count = await process_pending_pages_for_user(db, user_id=42)
        >>> # Result: 30 newest pages processed, 20 oldest still pending
    """
    # Get the user's processable pages, ordered newest first
    query = (
        db.query(Page)
        .join(Notebook, Notebook.id == Page.notebook_id)
        .filter(
            Notebook.user_id == user_id,
            _processable(datetime.utcnow()),
        )
        .order_by(Page.created_at.desc(), Page.id.desc())  # DESC = newest first!
    )
    if limit is not None:
        query = query.limit(limit)
    pending_pages = query.all()

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
        # Reserve quota before each page (stop if exhausted)
        if not quota_service.reserve_quota(db, user_id):
            logger.info(
                f"Quota exhausted after processing {processed_count} pages for user {user_id}. "
                f"Remaining {len(pending_pages) - processed_count - failed_count} pages still pending."
            )
            break

        try:
            # Download PDF from storage
            logger.debug(f"Downloading PDF for page {page.id}: {page.pdf_s3_key}")
            pdf_bytes = await storage.download_file(page.pdf_s3_key)

            # Run OCR
            logger.debug(f"Running OCR for page {page.id}")
            ocr_text = await ocr_service.extract_text_from_pdf(pdf_bytes)
        except Exception as e:
            # Provider text goes to the log only; the page gets a generic message.
            logger.warning(
                f"OCR failed for pending page {page.id} of user {user_id} "
                f"({type(e).__name__}: {e})",
                exc_info=True,
            )
            db.rollback()
            # Give the reserved unit back and schedule a retry (or give up)
            try:
                quota_service.release_quota(db, user_id)
                if not record_ocr_failure(page):
                    logger.warning(
                        f"Giving up OCR for page {page.id} of user {user_id} "
                        f"after {page.ocr_attempts} attempts"
                    )
                db.commit()
            except Exception as commit_error:
                logger.error(f"Failed to record OCR failure: {commit_error}")
                db.rollback()
            failed_count += 1
            # The provider is most likely down for every page: stop this batch.
            break

        if not ocr_text:
            # A blank page is a legitimate result; don't charge for it.
            quota_service.release_quota(db, user_id)

        page.ocr_text = ocr_text
        page.ocr_status = OcrStatus.COMPLETED
        page.ocr_completed_at = datetime.utcnow()
        page.ocr_error = None
        page.ocr_attempts = 0
        db.commit()
        processed_count += 1

        logger.info(
            f"Processed pending page {page.id} for user {user_id} "
            f"({processed_count}/{len(pending_pages)})"
        )

        # Same follow-up as an upload: Obsidian hash + queue for integrations
        notebook = db.get(Notebook, page.notebook_id)
        on_ocr_completed(db, page, notebook)

    logger.info(
        f"Retroactive processing complete for user {user_id}: "
        f"{processed_count} processed, {failed_count} failed, "
        f"{len(pending_pages) - processed_count - failed_count} still pending"
    )

    return processed_count


def _users_with_processable_pages(
    db: Session, *, after_user_id: int, limit: int
) -> list[int]:
    """User ids (> after_user_id, ascending) with processable pages and quota room.

    Processable: PENDING_QUOTA, or PENDING_RETRY with the backoff passed.

    "Room" means unlimited, ``used < limit``, or a period that has ended:
    ``reserve_quota`` resets the latter lazily, so it counts as available here.
    """
    now = datetime.utcnow()
    rows = (
        db.query(Notebook.user_id)
        .join(Page, Page.notebook_id == Notebook.id)
        .join(
            QuotaUsage,
            (QuotaUsage.user_id == Notebook.user_id)
            & (QuotaUsage.quota_type == QuotaType.OCR),
        )
        .filter(
            _processable(now),
            Notebook.user_id > after_user_id,
            or_(
                QuotaUsage.limit == -1,
                QuotaUsage.used < QuotaUsage.limit,
                QuotaUsage.reset_at <= now,
            ),
        )
        .group_by(Notebook.user_id)
        .order_by(Notebook.user_id)
        .limit(limit)
        .all()
    )
    return [row[0] for row in rows]


@contextmanager
def _user_claim(db: Session, user_id: int) -> Iterator[bool]:
    """Claim a user's pending pages for this worker; yields False if already claimed.

    Production runs several uvicorn workers, each with its own SyncWorker. Two
    of them working on the same user would OCR the same pages twice and race on
    the quota counter, so a user is processed by one worker at a time.

    On PostgreSQL the claim is a session-level advisory lock held on a dedicated
    connection (``pg_try_advisory_lock``, which never blocks). Holding it on its
    own connection matters: the ORM session commits per page, and a pooled
    session may switch connections between transactions. If the process dies,
    Postgres drops the connection and the lock with it, so nothing is left
    stuck. SQLite (local dev, tests) runs a single process, so no claim is needed.
    """
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        yield True
        return

    engine = getattr(bind, "engine", bind)
    conn = engine.connect()
    locked = False
    try:
        locked = bool(
            conn.execute(
                text("SELECT pg_try_advisory_lock(:cls, :uid)"),
                {"cls": PENDING_QUOTA_LOCK_CLASS, "uid": user_id},
            ).scalar()
        )
        conn.commit()
        yield locked
    finally:
        try:
            if locked:
                conn.execute(
                    text("SELECT pg_advisory_unlock(:cls, :uid)"),
                    {"cls": PENDING_QUOTA_LOCK_CLASS, "uid": user_id},
                )
                conn.commit()
        except Exception:
            # Never return a connection that may still hold the lock to the pool.
            logger.error(
                "Failed to release pending-quota claim for user %s", user_id, exc_info=True
            )
            conn.invalidate()
        finally:
            conn.close()


async def process_pending_quota_pages(
    db: Session,
    *,
    after_user_id: int = 0,
    max_users: int = MAX_USERS_PER_POLL,
    max_pages_per_user: int = MAX_PAGES_PER_USER,
) -> tuple[int, int]:
    """One bounded sweep of retroactive OCR, called by the sync worker each poll.

    Picks up to ``max_users`` users that have ``PENDING_QUOTA`` pages (or
    ``PENDING_RETRY`` pages that are due) and quota room again, round-robin by user id starting after ``after_user_id`` (so a
    user with a large backlog doesn't starve the others), claims each one, and
    OCRs up to ``max_pages_per_user`` of their pending pages, newest first.

    Args:
        db: Database session (owned and closed by the caller)
        after_user_id: Round-robin cursor returned by the previous sweep
        max_users: Users handled per sweep
        max_pages_per_user: Pages OCR'd per user per sweep

    Returns:
        (pages processed, cursor to pass as ``after_user_id`` next time)
    """
    user_ids = _users_with_processable_pages(db, after_user_id=after_user_id, limit=max_users)
    if not user_ids and after_user_id:
        # Reached the end of the id range: wrap around.
        user_ids = _users_with_processable_pages(db, after_user_id=0, limit=max_users)
    if not user_ids:
        return 0, 0

    processed = 0
    for user_id in user_ids:
        try:
            with _user_claim(db, user_id) as claimed:
                if not claimed:
                    logger.debug("Pending pages for user %s claimed by another worker", user_id)
                    continue
                processed += await process_pending_pages_for_user(
                    db, user_id, limit=max_pages_per_user
                )
        except Exception:
            db.rollback()
            logger.error("Retroactive OCR failed for user %s", user_id, exc_info=True)

    return processed, user_ids[-1]
