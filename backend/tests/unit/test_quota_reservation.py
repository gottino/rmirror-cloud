"""Atomic quota reservation and the shared post-OCR step.

- ``reserve_quota`` is one conditional UPDATE, so concurrent OCR jobs can't
  push ``used`` past ``limit``; ``release_quota`` refunds a failed or blank OCR.
- Both OCR paths (upload, retroactive worker) reserve before OCR, refund on
  failure/blank, and run ``on_ocr_completed``, which queues integration syncs
  based on OCR having produced text, not on quota left afterwards.
- A COMPLETED page with empty text is not re-OCR'd (and re-charged) when the
  same file is uploaded again.

The concurrency test needs PostgreSQL (SQLite serializes everything): set
``TEST_POSTGRES_URL`` to an empty, throwaway database to run it.
"""

import io
import os
import threading
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.auth.clerk import get_clerk_active_user
from app.database import Base
from app.dependencies import get_storage_service
from app.jobs import process_pending_pages as job
from app.models.notebook import Notebook
from app.models.page import OcrStatus, Page
from app.models.quota_usage import QuotaType, QuotaUsage
from app.models.subscription import SubscriptionTier
from app.models.sync_record import IntegrationConfig, SyncQueue
from app.models.user import User
from app.services import quota_service
from tests.conftest import create_test_page, create_user_with_quota
from tests.test_config import test_app  # noqa: F401 - fixture

PAGE_UUID = "5d0c6e2a-8b1f-4c3d-9e7a-2f4b6c8d0e1a"
NB_UUID = "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d"


def _quota(db: Session, user_id: int) -> QuotaUsage:
    db.expire_all()
    return db.query(QuotaUsage).filter_by(user_id=user_id, quota_type=QuotaType.OCR).one()


def _enable_notion(db: Session, user_id: int) -> None:
    db.add(
        IntegrationConfig(
            user_id=user_id, target_name="notion", is_enabled=True, config_encrypted="x"
        )
    )
    db.commit()


def _queued(db: Session, user_id: int) -> list[SyncQueue]:
    db.expire_all()
    return db.query(SyncQueue).filter_by(user_id=user_id, target_name="notion").all()


@pytest.fixture
def no_emails():
    with patch("app.services.quota_service.get_email_service") as get_email:
        yield get_email.return_value


# ---------------------------------------------------------------------------
# reserve_quota / release_quota
# ---------------------------------------------------------------------------


def test_reserve_is_a_single_conditional_update(db: Session, no_emails):
    """At limit-1 one reservation succeeds; at the limit the UPDATE matches no row."""
    user = create_user_with_quota(db, used=29, limit=30)
    quota_service.get_or_create_quota(db, user.id)  # warm: no lazy create/reset below

    updates: list[str] = []

    def record(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("UPDATE QUOTA_USAGE"):
            updates.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", record)
    try:
        assert quota_service.reserve_quota(db, user.id) is True
        assert len(updates) == 1
        assert _quota(db, user.id).used == 30

        updates.clear()
        assert quota_service.reserve_quota(db, user.id) is False
        assert len(updates) == 1  # still one statement; it just matched 0 rows
        assert _quota(db, user.id).used == 30
    finally:
        event.remove(engine, "before_cursor_execute", record)


def test_reserve_more_than_remaining_is_refused(db: Session, no_emails):
    user = create_user_with_quota(db, used=28, limit=30)
    assert quota_service.reserve_quota(db, user.id, amount=3) is False
    assert _quota(db, user.id).used == 28
    assert quota_service.reserve_quota(db, user.id, amount=2) is True
    assert _quota(db, user.id).used == 30


def test_reserve_unlimited_tier_does_not_count(db: Session, no_emails):
    user = create_user_with_quota(db, used=0, limit=-1, tier=SubscriptionTier.ENTERPRISE)
    for _ in range(3):
        assert quota_service.reserve_quota(db, user.id) is True
    assert _quota(db, user.id).used == 0
    quota_service.release_quota(db, user.id)
    assert _quota(db, user.id).used == 0


def test_reserve_applies_lazy_period_reset_first(db: Session, no_emails):
    user = create_user_with_quota(db, used=30, limit=30)
    quota = _quota(db, user.id)
    quota.reset_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()

    assert quota_service.reserve_quota(db, user.id) is True
    quota = _quota(db, user.id)
    assert quota.used == 1
    assert quota.reset_at > datetime.utcnow()


def test_release_refunds_and_never_goes_below_zero(db: Session, no_emails):
    user = create_user_with_quota(db, used=1, limit=30)
    quota_service.release_quota(db, user.id)
    assert _quota(db, user.id).used == 0
    quota_service.release_quota(db, user.id)
    assert _quota(db, user.id).used == 0


def test_reserve_sends_threshold_emails_once(db: Session, no_emails):
    user = create_user_with_quota(db, used=26, limit=30)

    assert quota_service.reserve_quota(db, user.id) is True  # 27/30 = 90%
    assert no_emails.send_quota_warning_email.call_count == 1
    assert quota_service.reserve_quota(db, user.id) is True  # 28/30
    assert quota_service.reserve_quota(db, user.id) is True  # 29/30
    assert no_emails.send_quota_warning_email.call_count == 1
    no_emails.send_quota_exceeded_email.assert_not_called()

    assert quota_service.reserve_quota(db, user.id) is True  # 30/30
    assert no_emails.send_quota_exceeded_email.call_count == 1
    assert quota_service.reserve_quota(db, user.id) is False
    assert no_emails.send_quota_exceeded_email.call_count == 1
    assert no_emails.send_quota_warning_email.call_count == 1


def test_reserve_without_subscription_raises_no_subscription_error(db: Session):
    user = User(email="nosub@example.com", clerk_user_id="clerk_nosub")
    db.add(user)
    db.commit()
    with pytest.raises(quota_service.NoSubscriptionError):
        quota_service.reserve_quota(db, user.id)


# ---------------------------------------------------------------------------
# Concurrency (PostgreSQL only)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("TEST_POSTGRES_URL"),
    reason="set TEST_POSTGRES_URL to an empty throwaway PostgreSQL database",
)
def test_concurrent_reservations_at_limit_minus_one_let_exactly_one_through():
    engine = create_engine(os.environ["TEST_POSTGRES_URL"], pool_size=20, max_overflow=0)
    with engine.begin() as conn:
        # The models declare trigram search indexes (as the migrations create them).
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    Base.metadata.create_all(engine)
    Sessions = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    threads_n = 12
    try:
        with Sessions() as setup:
            user_id = create_user_with_quota(setup, used=29, limit=30).id

        barrier = threading.Barrier(threads_n)
        results: list[bool] = []
        errors: list[BaseException] = []
        lock = threading.Lock()

        def worker():
            session = Sessions()
            try:
                quota_service.get_or_create_quota(session, user_id)
                session.commit()
                barrier.wait()
                ok = quota_service.reserve_quota(session, user_id)
                with lock:
                    results.append(ok)
            except BaseException as e:  # surface failures from threads
                with lock:
                    errors.append(e)
            finally:
                session.close()

        with patch("app.services.quota_service.get_email_service"):
            threads = [threading.Thread(target=worker) for _ in range(threads_n)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=60)

        assert errors == []
        assert len(results) == threads_n
        assert results.count(True) == 1
        with Sessions() as check:
            assert _quota(check, user_id).used == 30
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


# ---------------------------------------------------------------------------
# Upload path
# ---------------------------------------------------------------------------


@pytest.fixture
def upload(db, test_app, reset_rate_limiter):  # noqa: F811
    """Returns post(user, content, text) -> response, with OCR returning ``text``."""
    storage = MagicMock()
    storage.upload_file = AsyncMock()
    test_app.dependency_overrides[get_storage_service] = lambda: storage
    state: dict = {}

    async def _user():
        return state["user"]

    test_app.dependency_overrides[get_clerk_active_user] = _user

    converter = MagicMock()
    converter.has_content.return_value = True
    converter.rm_to_pdf_bytes.return_value = b"%PDF fake"
    ocr = MagicMock()
    ocr.extract_text_from_pdf = AsyncMock(return_value="Handwritten text")

    with patch("app.api.processing.RMConverter", return_value=converter), patch(
        "app.api.processing.OCRService", return_value=ocr
    ), patch("app.services.quota_service.get_email_service"), TestClient(test_app) as client:

        def post(user, content=b"page-v1", text="Handwritten text"):
            state["user"] = user
            if isinstance(text, BaseException):
                ocr.extract_text_from_pdf.side_effect = text
            else:
                ocr.extract_text_from_pdf.side_effect = None
                ocr.extract_text_from_pdf.return_value = text
            return client.post(
                "/v1/processing/rm-file",
                files={
                    "rm_file": (f"{PAGE_UUID}.rm", io.BytesIO(content), "application/octet-stream"),
                    "metadata_file": (
                        f"{NB_UUID}.metadata",
                        io.BytesIO(b'{"visibleName": "NB", "type": "DocumentType"}'),
                        "application/json",
                    ),
                },
            )

        post.ocr = ocr
        yield post


def _page(db: Session) -> Page:
    db.expire_all()
    return db.query(Page).filter_by(page_uuid=PAGE_UUID).one()


def test_upload_using_last_unit_is_queued_for_integrations(db: Session, upload):
    user = create_user_with_quota(db, used=29, limit=30)
    _enable_notion(db, user.id)

    resp = upload(user)

    assert resp.status_code == 200, resp.text
    assert _page(db).ocr_status == OcrStatus.COMPLETED
    assert _quota(db, user.id).used == 30
    queued = _queued(db, user.id)
    assert len(queued) == 1
    assert queued[0].item_id == str(_page(db).id)


def test_upload_with_exhausted_quota_is_not_queued(db: Session, upload):
    """Pages that were not OCR'd (PENDING_QUOTA) still never reach integrations."""
    user = create_user_with_quota(db, used=30, limit=30)
    _enable_notion(db, user.id)

    resp = upload(user)

    assert resp.status_code == 200, resp.text
    assert _page(db).ocr_status == OcrStatus.PENDING_QUOTA
    upload.ocr.extract_text_from_pdf.assert_not_awaited()
    assert _queued(db, user.id) == []
    assert _quota(db, user.id).used == 30


def test_blank_page_is_not_charged_or_reprocessed_on_reupload(db: Session, upload):
    user = create_user_with_quota(db, used=5, limit=30)
    _enable_notion(db, user.id)

    assert upload(user, text="").status_code == 200
    page = _page(db)
    assert page.ocr_status == OcrStatus.COMPLETED
    assert page.ocr_text == ""
    assert _quota(db, user.id).used == 5
    assert upload.ocr.extract_text_from_pdf.await_count == 1
    assert _queued(db, user.id) == []

    # Same file again: unchanged hash + COMPLETED -> no OCR, no charge
    assert upload(user, text="").status_code == 200
    assert upload.ocr.extract_text_from_pdf.await_count == 1
    assert _quota(db, user.id).used == 5

    # Changed content is OCR'd (and charged) as usual
    assert upload(user, content=b"page-v2", text="now with words").status_code == 200
    assert upload.ocr.extract_text_from_pdf.await_count == 2
    assert _quota(db, user.id).used == 6
    assert len(_queued(db, user.id)) == 1


def test_upload_ocr_failure_releases_reservation(db: Session, upload):
    user = create_user_with_quota(db, used=5, limit=30)

    resp = upload(user, text=RuntimeError("model down"))

    assert resp.status_code == 500
    assert _quota(db, user.id).used == 5


def test_upload_for_user_without_subscription_is_stored_pending(db: Session, upload, caplog):
    user = User(email="nosub-upload@example.com", clerk_user_id="clerk_nosub_upload")
    db.add(user)
    db.commit()
    db.refresh(user)

    with caplog.at_level("ERROR", logger="app.api.processing"):
        resp = upload(user)

    assert resp.status_code == 200, resp.text
    assert _page(db).ocr_status == OcrStatus.PENDING_QUOTA
    upload.ocr.extract_text_from_pdf.assert_not_awaited()
    assert any("no subscription" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# Retroactive OCR (sync worker job)
# ---------------------------------------------------------------------------


@pytest.fixture
def job_ocr():
    storage = MagicMock()
    storage.download_file = AsyncMock(return_value=b"%PDF")
    ocr = MagicMock()
    ocr.extract_text_from_pdf = AsyncMock(return_value="Recovered text")
    with patch.object(job, "get_storage_service", return_value=storage), patch.object(
        job, "OCRService", return_value=ocr
    ), patch("app.services.quota_service.get_email_service"):
        yield ocr


def _pending(db: Session, user_id: int, count: int) -> list[int]:
    notebook = Notebook(
        user_id=user_id, notebook_uuid=f"nb-r-{user_id}", visible_name="R", document_type="notebook"
    )
    db.add(notebook)
    db.commit()
    return [
        create_test_page(
            db,
            user_id=user_id,
            notebook_id=notebook.id,
            page_number=i + 1,
            ocr_status=OcrStatus.PENDING_QUOTA,
            created_at=datetime.utcnow() - timedelta(minutes=count - i),
        ).id
        for i in range(count)
    ]


@pytest.mark.asyncio
async def test_retroactive_ocr_queues_pages_for_integrations(db: Session, job_ocr):
    user = create_user_with_quota(db, used=29, limit=30)
    _enable_notion(db, user.id)
    page_ids = _pending(db, user.id, 2)

    processed = await job.process_pending_pages_for_user(db, user.id)

    assert processed == 1  # only one unit left: the newest page
    assert _quota(db, user.id).used == 30
    queued = _queued(db, user.id)
    assert [q.item_id for q in queued] == [str(page_ids[-1])]
    assert db.get(Page, page_ids[0]).ocr_status == OcrStatus.PENDING_QUOTA


@pytest.mark.asyncio
async def test_retroactive_blank_page_not_charged_or_queued(db: Session, job_ocr):
    user = create_user_with_quota(db, used=0, limit=30)
    _enable_notion(db, user.id)
    (page_id,) = _pending(db, user.id, 1)
    job_ocr.extract_text_from_pdf.return_value = ""

    await job.process_pending_pages_for_user(db, user.id)

    db.expire_all()
    page = db.get(Page, page_id)
    assert page.ocr_status == OcrStatus.COMPLETED
    assert page.ocr_text == ""
    assert _quota(db, user.id).used == 0
    assert _queued(db, user.id) == []


@pytest.mark.asyncio
async def test_retroactive_ocr_failure_releases_reservation(db: Session, job_ocr):
    user = create_user_with_quota(db, used=3, limit=30)
    (page_id,) = _pending(db, user.id, 1)
    job_ocr.extract_text_from_pdf.side_effect = RuntimeError("model down")

    await job.process_pending_pages_for_user(db, user.id)

    db.expire_all()
    assert db.get(Page, page_id).ocr_status == OcrStatus.FAILED
    assert _quota(db, user.id).used == 3
