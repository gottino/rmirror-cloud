"""Retroactive OCR of PENDING_QUOTA pages, run by the background sync worker.

Pages uploaded while a user's quota is exhausted are stored as PENDING_QUOTA.
``reset_quota()`` used to ``asyncio.create_task()`` the processing job from
request code, which raised (no running loop) and left the coroutine un-awaited,
so the job never ran. Now ``reset_quota()`` only resets the counter, and the
sync worker sweeps for users whose quota has room again each poll.
"""

import asyncio
import gc
import warnings
from types import SimpleNamespace
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.jobs import process_pending_pages as job
from app.models.notebook import Notebook
from app.models.page import OcrStatus, Page
from app.models.quota_usage import QuotaType, QuotaUsage
from app.services import quota_service
from app.services.sync_worker import SyncWorker
from tests.conftest import create_test_page, create_user_with_quota

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def ocr():
    """Mock OCR + storage used by the job; yields the OCR mock."""
    storage = MagicMock()
    storage.download_file = AsyncMock(side_effect=lambda key: f"pdf:{key}".encode())
    ocr_service = MagicMock()
    ocr_service.extract_text_from_pdf = AsyncMock(
        side_effect=lambda pdf: f"text for {pdf.decode()}"
    )
    with patch.object(job, "get_storage_service", return_value=storage), patch.object(
        job, "OCRService", return_value=ocr_service
    ):
        yield ocr_service


def _user(db: Session, *, used: int, limit: int, reset_at: datetime | None = None):
    user = create_user_with_quota(db, used=used, limit=limit)
    if reset_at is not None:
        quota = db.query(QuotaUsage).filter_by(user_id=user.id).one()
        quota.reset_at = reset_at
        db.commit()
    notebook = Notebook(
        user_id=user.id,
        notebook_uuid=f"nb-{user.id}",
        visible_name="Pending",
        document_type="notebook",
    )
    db.add(notebook)
    db.commit()
    # Plain values: the worker step closes the session, detaching ORM objects
    return SimpleNamespace(id=user.id), SimpleNamespace(id=notebook.id)


def _pending_pages(db: Session, user, notebook, count: int) -> list[SimpleNamespace]:
    """``count`` PENDING_QUOTA pages, oldest first (page i is i days newer)."""
    base = datetime.utcnow() - timedelta(days=count + 1)
    pages = [
        create_test_page(
            db,
            user_id=user.id,
            notebook_id=notebook.id,
            page_number=notebook.id * 100 + i,
            ocr_status=OcrStatus.PENDING_QUOTA,
            created_at=base + timedelta(days=i),
        )
        for i in range(count)
    ]
    return [SimpleNamespace(id=p.id, pdf_s3_key=p.pdf_s3_key) for p in pages]


def _status(db: Session, pages: list[SimpleNamespace]) -> list[str]:
    db.expire_all()
    return [db.get(Page, p.id).ocr_status for p in pages]


def _quota(db: Session, user) -> QuotaUsage:
    db.expire_all()
    return db.query(QuotaUsage).filter_by(user_id=user.id, quota_type=QuotaType.OCR).one()


async def _run_worker_step(db: Session, worker: SyncWorker | None = None) -> SyncWorker:
    worker = worker or SyncWorker()
    with patch("app.services.sync_worker.SessionLocal", return_value=db):
        await worker._process_pending_quota_pages()
    return worker


# ---------------------------------------------------------------------------
# reset_quota no longer spawns background work
# ---------------------------------------------------------------------------


def _assert_reset_schedules_nothing(db: Session):
    user = create_user_with_quota(db, used=30, limit=30)
    with patch.object(job, "process_pending_pages_for_user") as spawned, warnings.catch_warnings(
        record=True
    ) as caught:
        warnings.simplefilter("always")
        quota = quota_service.reset_quota(db, user.id)
        gc.collect()  # "never awaited" is reported when the coroutine is collected

    assert quota.used == 0
    spawned.assert_not_called()
    runtime = [w for w in caught if issubclass(w.category, RuntimeWarning)]
    assert runtime == [], [str(w.message) for w in runtime]


def test_reset_quota_without_event_loop_emits_no_runtime_warning(db: Session):
    _assert_reset_schedules_nothing(db)


@pytest.mark.asyncio
async def test_reset_quota_inside_event_loop_spawns_no_task(db: Session):
    tasks_before = asyncio.all_tasks()
    _assert_reset_schedules_nothing(db)
    assert asyncio.all_tasks() == tasks_before


def test_lazy_reset_via_check_quota_emits_no_runtime_warning(db: Session):
    """The real call path: get_or_create_quota resets an expired period."""
    user = create_user_with_quota(db, used=30, limit=30)
    quota = _quota(db, user)
    quota.reset_at = datetime.utcnow() - timedelta(minutes=1)
    db.commit()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert quota_service.check_quota(db, user.id) is True
        gc.collect()

    assert not [w for w in caught if issubclass(w.category, RuntimeWarning)]


# ---------------------------------------------------------------------------
# Worker step
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_worker_processes_pending_pages_newest_first(db: Session, ocr):
    user, notebook = _user(db, used=0, limit=30)
    pages = _pending_pages(db, user, notebook, 8)
    per_poll = job.MAX_PAGES_PER_USER  # 5

    await _run_worker_step(db)

    statuses = _status(db, pages)
    # Oldest 3 untouched, newest 5 OCR'd
    assert statuses[: 8 - per_poll] == [OcrStatus.PENDING_QUOTA] * (8 - per_poll)
    assert statuses[8 - per_poll :] == [OcrStatus.COMPLETED] * per_poll
    # ...and in newest-first order
    keys = [c.args[0] for c in ocr.extract_text_from_pdf.await_args_list]
    expected = [f"pdf:{p.pdf_s3_key}".encode() for p in reversed(pages[8 - per_poll :])]
    assert keys == expected
    assert db.get(Page, pages[-1].id).ocr_text == f"text for pdf:{pages[-1].pdf_s3_key}"
    assert _quota(db, user).used == per_poll

    # Next poll picks up the remaining (older) pages
    await _run_worker_step(db)
    assert _status(db, pages) == [OcrStatus.COMPLETED] * 8
    assert _quota(db, user).used == 8


@pytest.mark.asyncio
async def test_worker_stops_at_quota_limit(db: Session, ocr):
    user, notebook = _user(db, used=28, limit=30)
    pages = _pending_pages(db, user, notebook, 5)

    await _run_worker_step(db)

    assert _status(db, pages) == [OcrStatus.PENDING_QUOTA] * 3 + [OcrStatus.COMPLETED] * 2
    assert ocr.extract_text_from_pdf.await_count == 2
    assert _quota(db, user).used == 30

    # Quota now exhausted: further polls leave the rest alone
    await _run_worker_step(db)
    assert ocr.extract_text_from_pdf.await_count == 2
    assert _status(db, pages)[:3] == [OcrStatus.PENDING_QUOTA] * 3


@pytest.mark.asyncio
async def test_worker_leaves_pages_alone_without_remaining_quota(db: Session, ocr):
    user, notebook = _user(db, used=30, limit=30)
    pages = _pending_pages(db, user, notebook, 3)

    await _run_worker_step(db)

    assert _status(db, pages) == [OcrStatus.PENDING_QUOTA] * 3
    ocr.extract_text_from_pdf.assert_not_awaited()
    assert _quota(db, user).used == 30


@pytest.mark.asyncio
async def test_worker_processes_after_period_ends(db: Session, ocr):
    """An exhausted quota whose period ended is reset lazily, then OCR resumes."""
    user, notebook = _user(
        db, used=30, limit=30, reset_at=datetime.utcnow() - timedelta(minutes=1)
    )
    pages = _pending_pages(db, user, notebook, 3)

    await _run_worker_step(db)

    assert _status(db, pages) == [OcrStatus.COMPLETED] * 3
    quota = _quota(db, user)
    assert quota.used == 3
    assert quota.reset_at > datetime.utcnow()


@pytest.mark.asyncio
async def test_failed_ocr_does_not_consume_quota(db: Session, ocr):
    user, notebook = _user(db, used=0, limit=30)
    pages = _pending_pages(db, user, notebook, 2)
    ocr.extract_text_from_pdf.side_effect = [RuntimeError("model down"), "ok text"]

    await _run_worker_step(db)

    # Newest first: the newest page failed, the older one succeeded
    assert _status(db, pages) == [OcrStatus.COMPLETED, OcrStatus.FAILED]
    assert _quota(db, user).used == 1


@pytest.mark.asyncio
async def test_worker_skips_users_claimed_by_another_worker(db: Session, ocr):
    from contextlib import contextmanager

    user, notebook = _user(db, used=0, limit=30)
    pages = _pending_pages(db, user, notebook, 2)

    @contextmanager
    def already_claimed(_db, _user_id):
        yield False

    with patch.object(job, "_user_claim", already_claimed):
        await _run_worker_step(db)

    assert _status(db, pages) == [OcrStatus.PENDING_QUOTA] * 2
    ocr.extract_text_from_pdf.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_round_robins_across_users(db: Session, ocr):
    """With one user per poll, a big backlog doesn't starve other users."""
    big, big_nb = _user(db, used=0, limit=100)
    small, small_nb = _user(db, used=0, limit=100)
    big_pages = _pending_pages(db, big, big_nb, 20)
    small_pages = _pending_pages(db, small, small_nb, 1)

    cursor = 0
    for _ in range(2):
        _, cursor = await job.process_pending_quota_pages(
            db, after_user_id=cursor, max_users=1, max_pages_per_user=5
        )

    assert _status(db, small_pages) == [OcrStatus.COMPLETED]
    assert _status(db, big_pages).count(OcrStatus.COMPLETED) == 5

    # Cursor wraps back to the first user once the id range is exhausted
    _, cursor = await job.process_pending_quota_pages(
        db, after_user_id=cursor, max_users=1, max_pages_per_user=5
    )
    assert cursor == big.id
    assert _status(db, big_pages).count(OcrStatus.COMPLETED) == 10


@pytest.mark.asyncio
async def test_worker_step_closes_its_session(ocr):
    session = MagicMock()
    with patch(
        "app.jobs.process_pending_pages.process_pending_quota_pages",
        AsyncMock(side_effect=RuntimeError("boom")),
    ):
        with patch("app.services.sync_worker.SessionLocal", return_value=session):
            await SyncWorker()._process_pending_quota_pages()
    session.close.assert_called_once()


# ---------------------------------------------------------------------------
# Per-user claim (Postgres advisory lock on a dedicated connection)
# ---------------------------------------------------------------------------


def _pg_session(lock_result: bool):
    conn = MagicMock()
    conn.execute.return_value.scalar.return_value = lock_result
    engine = MagicMock()
    engine.dialect.name = "postgresql"
    engine.engine = engine
    engine.connect.return_value = conn
    session = MagicMock()
    session.get_bind.return_value = engine
    return session, conn


def _sql(call) -> str:
    return str(call.args[0])


def test_user_claim_acquires_and_releases_advisory_lock():
    session, conn = _pg_session(True)

    with job._user_claim(session, 42) as claimed:
        assert claimed is True
        assert "pg_try_advisory_lock" in _sql(conn.execute.call_args_list[0])

    assert "pg_advisory_unlock" in _sql(conn.execute.call_args_list[-1])
    assert conn.execute.call_args_list[-1].args[1] == {
        "cls": job.PENDING_QUOTA_LOCK_CLASS,
        "uid": 42,
    }
    conn.close.assert_called_once()


def test_user_claim_reports_lock_held_elsewhere():
    session, conn = _pg_session(False)

    with job._user_claim(session, 42) as claimed:
        assert claimed is False

    assert not any("pg_advisory_unlock" in _sql(c) for c in conn.execute.call_args_list)
    conn.close.assert_called_once()


def test_user_claim_invalidates_connection_if_unlock_fails():
    session, conn = _pg_session(True)

    with job._user_claim(session, 42):
        conn.execute.side_effect = RuntimeError("connection lost")

    conn.invalidate.assert_called_once()
    conn.close.assert_called_once()


def test_user_claim_is_a_noop_on_sqlite(db: Session):
    with job._user_claim(db, 1) as claimed:
        assert claimed is True
