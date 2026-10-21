"""Tests for debounced combined-notebook-PDF rebuilds.

The combined notebook PDF used to be rebuilt synchronously inside every
single-page upload, which made a full N-page sync O(N^2) in S3 downloads (each
page upload re-downloaded and re-stitched every page). Now an upload only marks
the notebook dirty (``pdf_dirty_at``), and the background worker rebuilds once
the notebook has been quiet for a debounce window — collapsing a burst of N
uploads into a single rebuild.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.models.notebook import Notebook
from app.models.notebook_page import NotebookPage
from app.models.page import OcrStatus, Page
from app.models.user import User
from app.services.notebook_pdf import (
    PDF_REBUILD_CLAIM_SECONDS,
    rebuild_combined_pdf,
    rebuild_dirty_notebook_pdfs,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_storage() -> MagicMock:
    storage = MagicMock()
    storage.download_file = AsyncMock(return_value=b"%PDF-1.4 page")
    storage.upload_file = AsyncMock(return_value=True)
    storage.delete_file = AsyncMock(return_value=True)
    return storage


@pytest.fixture
def user(db: Session) -> User:
    u = User(
        email="pdf-rebuild@example.com",
        full_name="PDF Rebuild User",
        clerk_user_id="clerk_pdf_rebuild",
        is_active=True,
        is_verified=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _create_notebook(db: Session, user: User, *, pdf_dirty_at=None) -> Notebook:
    nb = Notebook(
        user_id=user.id,
        notebook_uuid=f"nb-{datetime.utcnow().timestamp()}",
        visible_name="NB",
        document_type="notebook",
        pdf_dirty_at=pdf_dirty_at,
    )
    db.add(nb)
    db.commit()
    db.refresh(nb)
    return nb


def _add_page(db: Session, nb: Notebook, page_number: int, pdf_s3_key="pages/p.pdf") -> Page:
    page = Page(
        notebook_id=nb.id,
        page_uuid=f"page-{page_number}-{datetime.utcnow().timestamp()}",
        ocr_status=OcrStatus.COMPLETED,
        ocr_text="text",
        pdf_s3_key=pdf_s3_key,
    )
    db.add(page)
    db.commit()
    db.refresh(page)
    db.add(NotebookPage(notebook_id=nb.id, page_id=page.id, page_number=page_number))
    db.commit()
    return page


# ---------------------------------------------------------------------------
# rebuild_combined_pdf
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rebuild_downloads_each_page_once_and_uploads_one_combined_pdf(db, user):
    nb = _create_notebook(db, user)
    for n in range(1, 4):
        _add_page(db, nb, n)
    storage = _make_storage()

    with patch(
        "app.services.notebook_pdf.PDFService.combine_page_pdfs",
        return_value=b"%PDF combined",
    ) as combine:
        rebuilt = await rebuild_combined_pdf(db, storage, nb)

    assert rebuilt is True
    # One download per page, exactly one combine + one upload for the notebook.
    assert storage.download_file.await_count == 3
    assert storage.upload_file.await_count == 1
    combine.assert_called_once()
    assert nb.notebook_pdf_s3_key is not None


@pytest.mark.asyncio
async def test_rebuild_with_no_pdf_pages_is_noop(db, user):
    nb = _create_notebook(db, user)
    _add_page(db, nb, 1, pdf_s3_key=None)  # page exists but has no PDF
    storage = _make_storage()

    rebuilt = await rebuild_combined_pdf(db, storage, nb)

    assert rebuilt is False
    storage.upload_file.assert_not_awaited()


# ---------------------------------------------------------------------------
# rebuild_dirty_notebook_pdfs (the debounce sweep)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sweep_skips_notebook_still_within_debounce_window(db, user):
    now = datetime(2026, 6, 5, 12, 0, 0)
    nb = _create_notebook(db, user, pdf_dirty_at=now - timedelta(seconds=10))
    _add_page(db, nb, 1)
    storage = _make_storage()

    count = await rebuild_dirty_notebook_pdfs(db, storage, debounce_seconds=60, now=now)

    assert count == 0
    storage.upload_file.assert_not_awaited()
    db.refresh(nb)
    assert nb.pdf_dirty_at is not None  # still pending


@pytest.mark.asyncio
async def test_sweep_rebuilds_notebook_past_debounce_window(db, user):
    now = datetime(2026, 6, 5, 12, 0, 0)
    nb = _create_notebook(db, user, pdf_dirty_at=now - timedelta(seconds=120))
    _add_page(db, nb, 1)
    storage = _make_storage()

    with patch(
        "app.services.notebook_pdf.PDFService.combine_page_pdfs",
        return_value=b"%PDF combined",
    ):
        count = await rebuild_dirty_notebook_pdfs(db, storage, debounce_seconds=60, now=now)

    assert count == 1
    storage.upload_file.assert_awaited_once()
    db.refresh(nb)
    assert nb.pdf_dirty_at is None  # cleared after rebuild


@pytest.mark.asyncio
async def test_sweep_ignores_clean_notebooks(db, user):
    now = datetime(2026, 6, 5, 12, 0, 0)
    nb = _create_notebook(db, user, pdf_dirty_at=None)
    _add_page(db, nb, 1)
    storage = _make_storage()

    count = await rebuild_dirty_notebook_pdfs(db, storage, debounce_seconds=60, now=now)

    assert count == 0
    storage.upload_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_burst_of_uploads_collapses_to_a_single_rebuild(db, user):
    """While pages keep arriving (pdf_dirty_at keeps bumping forward) no rebuild
    happens; once the notebook goes quiet for the window, it rebuilds exactly once."""
    base = datetime(2026, 6, 5, 12, 0, 0)
    nb = _create_notebook(db, user, pdf_dirty_at=base)
    _add_page(db, nb, 1)
    storage = _make_storage()

    with patch(
        "app.services.notebook_pdf.PDFService.combine_page_pdfs",
        return_value=b"%PDF combined",
    ):
        # Pages keep arriving every 10s; each sweep runs 30s of debounce later
        # but the last change is always < 60s ago, so nothing rebuilds yet.
        for i in range(5):
            nb.pdf_dirty_at = base + timedelta(seconds=10 * i)  # new page arrives
            db.commit()
            sweep_now = base + timedelta(seconds=10 * i + 30)
            count = await rebuild_dirty_notebook_pdfs(
                db, storage, debounce_seconds=60, now=sweep_now
            )
            assert count == 0
        storage.upload_file.assert_not_awaited()

        # Uploads stop; 60s after the last page, the sweep rebuilds once.
        quiet_now = base + timedelta(seconds=10 * 4 + 61)
        count = await rebuild_dirty_notebook_pdfs(
            db, storage, debounce_seconds=60, now=quiet_now
        )

    assert count == 1
    storage.upload_file.assert_awaited_once()
    db.refresh(nb)
    assert nb.pdf_dirty_at is None


# ---------------------------------------------------------------------------
# Concurrency and failure handling
# ---------------------------------------------------------------------------

COMBINE = "app.services.notebook_pdf.PDFService.combine_page_pdfs"
BUILD = "app.services.notebook_pdf._build_and_upload_off_loop"


@pytest.mark.asyncio
async def test_page_uploaded_during_rebuild_keeps_notebook_dirty(db, user):
    """An upload landing mid-rebuild must not be wiped by clearing the flag."""
    now = datetime(2026, 6, 5, 12, 0, 0)
    nb = _create_notebook(db, user, pdf_dirty_at=now - timedelta(seconds=120))
    _add_page(db, nb, 1)
    upload_time = now + timedelta(seconds=2)

    async def build_while_a_page_arrives(storage, page_keys, dest_key):
        # What processing.py does when another page is uploaded meanwhile
        db.query(Notebook).filter(Notebook.id == nb.id).update({Notebook.pdf_dirty_at: upload_time})
        db.commit()
        return len(page_keys)

    with patch(BUILD, side_effect=build_while_a_page_arrives):
        count = await rebuild_dirty_notebook_pdfs(db, _make_storage(), debounce_seconds=60, now=now)

    assert count == 1
    db.refresh(nb)
    assert nb.pdf_dirty_at == upload_time  # still dirty: rebuilt again on a later sweep


@pytest.mark.asyncio
async def test_failed_rebuild_backs_off_instead_of_retrying_every_poll(db, user):
    now = datetime(2026, 6, 5, 12, 0, 0)
    nb = _create_notebook(db, user, pdf_dirty_at=now - timedelta(seconds=120))
    _add_page(db, nb, 1)
    storage = _make_storage()
    storage.upload_file = AsyncMock(side_effect=RuntimeError("S3 unavailable"))

    with patch(COMBINE, return_value=b"%PDF combined"):
        assert await rebuild_dirty_notebook_pdfs(db, storage, debounce_seconds=60, now=now) == 0
        assert storage.upload_file.await_count == 1

        # The next polls skip it while the claim is outstanding...
        soon = now + timedelta(seconds=5)
        assert await rebuild_dirty_notebook_pdfs(db, storage, debounce_seconds=60, now=soon) == 0
        assert storage.upload_file.await_count == 1

        # ...and it is retried once the claim has expired.
        storage.upload_file = AsyncMock(return_value=True)
        later = now + timedelta(seconds=PDF_REBUILD_CLAIM_SECONDS + 61)
        assert await rebuild_dirty_notebook_pdfs(db, storage, debounce_seconds=60, now=later) == 1

    db.refresh(nb)
    assert nb.pdf_dirty_at is None


@pytest.mark.asyncio
async def test_missing_page_pdf_is_left_out_not_fatal(db, user):
    now = datetime(2026, 6, 5, 12, 0, 0)
    nb = _create_notebook(db, user, pdf_dirty_at=now - timedelta(seconds=120))
    for n in (1, 2, 3):
        _add_page(db, nb, n, pdf_s3_key=f"pages/{n}.pdf")
    storage = _make_storage()
    storage.download_file = AsyncMock(side_effect=[b"%PDF 1", FileNotFoundError("pages/2.pdf"), b"%PDF 3"])

    with patch(COMBINE, return_value=b"%PDF combined") as combine:
        count = await rebuild_dirty_notebook_pdfs(db, storage, debounce_seconds=60, now=now)

    assert count == 1
    combine.assert_called_once_with([b"%PDF 1", b"%PDF 3"])
    db.refresh(nb)
    assert nb.pdf_dirty_at is None


@pytest.mark.asyncio
async def test_notebook_deleted_during_rebuild_does_not_orphan_its_pdf(db, user):
    now = datetime(2026, 6, 5, 12, 0, 0)
    nb = _create_notebook(db, user, pdf_dirty_at=now - timedelta(seconds=120))
    _add_page(db, nb, 1)
    nb_id = nb.id
    expected_key = f"users/{user.id}/notebooks/{nb.notebook_uuid}/notebook.pdf"
    storage = _make_storage()

    async def build_then_notebook_is_deleted(storage, page_keys, dest_key):
        db.query(NotebookPage).filter(NotebookPage.notebook_id == nb_id).delete()
        db.query(Notebook).filter(Notebook.id == nb_id).delete()
        db.commit()
        return len(page_keys)

    with patch(BUILD, side_effect=build_then_notebook_is_deleted):
        count = await rebuild_dirty_notebook_pdfs(db, storage, debounce_seconds=60, now=now)

    assert count == 0
    storage.delete_file.assert_awaited_once_with(expected_key)
