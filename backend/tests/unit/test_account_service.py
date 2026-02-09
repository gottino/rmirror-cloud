"""Tests for AccountService: data export, account deletion, and data summary."""

import json
import zipfile
from datetime import datetime, timedelta
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.models.notebook import Notebook
from app.models.notebook_page import NotebookPage
from app.models.page import OcrStatus, Page
from app.models.subscription import Subscription, SubscriptionStatus, SubscriptionTier
from app.models.sync_record import IntegrationConfig, SyncQueue
from app.models.user import User
from app.services.account_service import AccountService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_user(db: Session, email: str = "test@example.com") -> User:
    user = User(
        email=email,
        full_name="Test User",
        clerk_user_id=f"clerk_{email}",
        subscription_tier=SubscriptionTier.FREE,
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_notebook(
    db: Session,
    user: User,
    name: str = "Test Notebook",
    document_type: str = "notebook",
    full_path: str | None = None,
    s3_key: str | None = None,
    notebook_pdf_s3_key: str | None = None,
) -> Notebook:
    nb = Notebook(
        user_id=user.id,
        notebook_uuid=f"nb-{name}-{datetime.utcnow().timestamp()}",
        visible_name=name,
        document_type=document_type,
        full_path=full_path,
        s3_key=s3_key,
        notebook_pdf_s3_key=notebook_pdf_s3_key,
    )
    db.add(nb)
    db.commit()
    db.refresh(nb)
    return nb


def _create_page(
    db: Session,
    notebook: Notebook,
    page_number: int = 1,
    ocr_status: str = OcrStatus.COMPLETED,
    ocr_text: str | None = "Test OCR text",
    pdf_s3_key: str | None = "pages/test.pdf",
    s3_key: str | None = "pages/test.rm",
) -> tuple[Page, NotebookPage]:
    page = Page(
        notebook_id=notebook.id,
        page_uuid=f"page-{page_number}-{datetime.utcnow().timestamp()}",
        ocr_status=ocr_status,
        ocr_text=ocr_text,
        pdf_s3_key=pdf_s3_key,
        s3_key=s3_key,
    )
    db.add(page)
    db.commit()
    db.refresh(page)

    nb_page = NotebookPage(
        notebook_id=notebook.id,
        page_id=page.id,
        page_number=page_number,
    )
    db.add(nb_page)
    db.commit()
    db.refresh(nb_page)

    return page, nb_page


def _mock_storage() -> MagicMock:
    storage = MagicMock()
    storage.download_file = AsyncMock(return_value=b"%PDF-1.4 fake pdf")
    storage.delete_file = AsyncMock(return_value=True)
    return storage


# ---------------------------------------------------------------------------
# get_data_summary tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_data_summary_counts(db: Session):
    """Verify correct counts are returned."""
    user = _create_user(db)
    nb1 = _create_notebook(db, user, "NB1", s3_key="nb1.zip")
    nb2 = _create_notebook(db, user, "NB2", notebook_pdf_s3_key="nb2.pdf")
    _create_page(db, nb1, 1)
    _create_page(db, nb1, 2)
    _create_page(db, nb2, 1, pdf_s3_key=None, s3_key=None)

    summary = await AccountService.get_data_summary(user.id, db)

    assert summary["notebooks"] == 2
    assert summary["pages"] == 3
    # nb1: s3_key(1) + page1: pdf+rm(2) + page2: pdf+rm(2) + nb2: notebook_pdf(1) + page3: 0 = 6
    assert summary["files"] == 6
    assert summary["subscription"] == "free"
    assert summary["member_since"] is not None


@pytest.mark.asyncio
async def test_data_summary_empty_account(db: Session):
    """User with no notebooks."""
    user = _create_user(db)
    summary = await AccountService.get_data_summary(user.id, db)

    assert summary["notebooks"] == 0
    assert summary["pages"] == 0
    assert summary["files"] == 0
    assert summary["integrations"] == []


@pytest.mark.asyncio
async def test_data_summary_with_integrations(db: Session):
    """Verify integrations are listed."""
    user = _create_user(db)

    # Need to mock encryption since IntegrationConfig requires it
    ic = IntegrationConfig(
        user_id=user.id,
        target_name="notion",
        config_encrypted="encrypted-data",
    )
    db.add(ic)
    db.commit()

    summary = await AccountService.get_data_summary(user.id, db)
    assert summary["integrations"] == ["notion"]


# ---------------------------------------------------------------------------
# generate_data_export tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_data_export(db: Session):
    """Creates user with 2 notebooks, verifies ZIP structure."""
    user = _create_user(db)
    nb1 = _create_notebook(db, user, "My Notebook", full_path="My Notebook")
    nb2 = _create_notebook(db, user, "Work Notes", full_path="Work/Work Notes")

    _create_page(db, nb1, 1, ocr_text="Page 1 text")
    _create_page(db, nb1, 2, ocr_text="Page 2 text")
    _create_page(db, nb2, 1, ocr_text="Work page text")

    storage = _mock_storage()

    with patch("app.services.account_service.PDFService") as mock_pdf:
        mock_pdf.combine_page_pdfs.return_value = b"%PDF-combined"
        zip_bytes = await AccountService.generate_data_export(user.id, db, storage)

    # Verify ZIP contents
    zf = zipfile.ZipFile(BytesIO(zip_bytes))
    names = zf.namelist()

    assert "rmirror-export/README.txt" in names
    assert "rmirror-export/metadata.json" in names

    # Check that notebook folders exist
    nb1_txt = [n for n in names if "My_Notebook" in n and n.endswith(".txt")]
    nb2_txt = [n for n in names if "Work_Notes" in n and n.endswith(".txt")]
    assert len(nb1_txt) == 1
    assert len(nb2_txt) == 1

    # Check metadata
    metadata = json.loads(zf.read("rmirror-export/metadata.json"))
    assert metadata["email"] == "test@example.com"
    assert metadata["notebook_count"] == 2
    assert metadata["total_pages"] == 3


@pytest.mark.asyncio
async def test_export_empty_account(db: Session):
    """User with no notebooks - ZIP contains metadata only."""
    user = _create_user(db)
    storage = _mock_storage()

    zip_bytes = await AccountService.generate_data_export(user.id, db, storage)

    zf = zipfile.ZipFile(BytesIO(zip_bytes))
    names = zf.namelist()
    assert "rmirror-export/metadata.json" in names
    assert "rmirror-export/README.txt" in names

    metadata = json.loads(zf.read("rmirror-export/metadata.json"))
    assert metadata["notebook_count"] == 0
    assert metadata["total_pages"] == 0


@pytest.mark.asyncio
async def test_export_notebook_no_pdfs(db: Session):
    """Pages without PDFs in storage get placeholder PDFs."""
    user = _create_user(db)
    nb = _create_notebook(db, user, "Text Only", full_path="Text Only")
    _create_page(db, nb, 1, ocr_text="Has text", pdf_s3_key=None, s3_key=None)

    storage = _mock_storage()
    storage.download_file = AsyncMock(side_effect=FileNotFoundError("Not found"))

    with patch("app.services.account_service.PDFService") as mock_pdf:
        mock_pdf.create_placeholder_pdf.return_value = b"%PDF-placeholder"
        mock_pdf.combine_page_pdfs.return_value = b"%PDF-combined"
        zip_bytes = await AccountService.generate_data_export(user.id, db, storage)

    zf = zipfile.ZipFile(BytesIO(zip_bytes))
    names = zf.namelist()

    # Should have both text and PDF (with placeholder)
    txt_files = [n for n in names if n.endswith(".txt") and "Text_Only" in n]
    pdf_files = [n for n in names if n.endswith(".pdf") and "Text_Only" in n]
    assert len(txt_files) == 1
    assert len(pdf_files) == 1
    mock_pdf.create_placeholder_pdf.assert_called_once()


@pytest.mark.asyncio
async def test_export_pages_no_ocr_text(db: Session):
    """Pages with no OCR text include placeholder."""
    user = _create_user(db)
    nb = _create_notebook(db, user, "No OCR", full_path="No OCR")
    _create_page(db, nb, 1, ocr_text=None, ocr_status=OcrStatus.PENDING)

    storage = _mock_storage()

    with patch("app.services.account_service.PDFService") as mock_pdf:
        mock_pdf.combine_page_pdfs.return_value = b"%PDF-combined"
        zip_bytes = await AccountService.generate_data_export(user.id, db, storage)

    zf = zipfile.ZipFile(BytesIO(zip_bytes))
    txt_files = [n for n in zf.namelist() if n.endswith(".txt") and "No_OCR" in n]
    assert len(txt_files) == 1

    content = zf.read(txt_files[0]).decode("utf-8")
    assert "[No OCR text]" in content


# ---------------------------------------------------------------------------
# delete_account tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_pages_without_pdf_get_placeholders(db: Session):
    """Pages with OCR text but no PDF get placeholder PDFs in export."""
    user = _create_user(db)
    nb = _create_notebook(db, user, "Mixed Pages", full_path="Mixed Pages")

    # Page 1: fully OCR'd with PDF
    _create_page(db, nb, 1, ocr_text="First page text", pdf_s3_key="pages/p1.pdf")

    # Page 2: has OCR text but no PDF (common case: old pipeline)
    _create_page(db, nb, 2, ocr_text="Second page text", pdf_s3_key=None, s3_key=None)

    # Page 3: fully OCR'd with PDF
    _create_page(db, nb, 3, ocr_text="Third page text", pdf_s3_key="pages/p3.pdf")

    storage = _mock_storage()

    with patch("app.services.account_service.PDFService") as mock_pdf:
        mock_pdf.combine_page_pdfs.return_value = b"%PDF-combined"
        mock_pdf.create_placeholder_pdf.return_value = b"%PDF-placeholder"
        zip_bytes = await AccountService.generate_data_export(user.id, db, storage)

    # Verify placeholder was generated for page 2 (no pdf_s3_key)
    mock_pdf.create_placeholder_pdf.assert_called_once()
    placeholder_text = mock_pdf.create_placeholder_pdf.call_args[0][0]
    assert "Content not available" in placeholder_text

    # Verify combine_page_pdfs received 3 items (2 real + 1 placeholder)
    mock_pdf.combine_page_pdfs.assert_called_once()
    pdf_list = mock_pdf.combine_page_pdfs.call_args[0][0]
    assert len(pdf_list) == 3

    # Verify text export includes all 3 pages with their OCR text
    zf = zipfile.ZipFile(BytesIO(zip_bytes))
    txt_files = [n for n in zf.namelist() if n.endswith(".txt") and "Mixed_Pages" in n]
    assert len(txt_files) == 1

    content = zf.read(txt_files[0]).decode("utf-8")
    assert "First page text" in content
    assert "Second page text" in content
    assert "Third page text" in content

    # Verify metadata page count
    metadata = json.loads(zf.read("rmirror-export/metadata.json"))
    assert metadata["total_pages"] == 3


@pytest.mark.asyncio
async def test_delete_account_cascade(db: Session):
    """Create user with full data graph, delete, verify all tables are empty."""
    user = _create_user(db)
    sub = Subscription(
        user_id=user.id,
        tier=SubscriptionTier.FREE,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=datetime.utcnow(),
        current_period_end=datetime.utcnow() + timedelta(days=30),
    )
    db.add(sub)
    nb = _create_notebook(db, user, "Del Test")
    _create_page(db, nb, 1)
    _create_page(db, nb, 2)
    db.commit()

    storage = _mock_storage()
    result = await AccountService.delete_account(user.id, db, storage)

    assert result["deleted_notebooks"] == 1
    assert result["deleted_pages"] == 2

    # Verify user is gone
    assert db.query(User).filter(User.id == user.id).first() is None
    # Verify notebooks are gone
    assert db.query(Notebook).filter(Notebook.user_id == user.id).count() == 0
    # Verify subscription is gone
    assert db.query(Subscription).filter(Subscription.user_id == user.id).count() == 0


@pytest.mark.asyncio
async def test_delete_account_s3_cleanup(db: Session):
    """Mock storage service, verify delete_file called for each S3 key."""
    user = _create_user(db)
    nb = _create_notebook(db, user, "S3 Test", s3_key="nb/orig.zip", notebook_pdf_s3_key="nb/combined.pdf")
    _create_page(db, nb, 1, pdf_s3_key="pages/p1.pdf", s3_key="pages/p1.rm")
    _create_page(db, nb, 2, pdf_s3_key="pages/p2.pdf", s3_key=None)

    storage = _mock_storage()
    await AccountService.delete_account(user.id, db, storage)

    # Expected keys: nb/orig.zip, nb/combined.pdf, pages/p1.pdf, pages/p1.rm, pages/p2.pdf
    assert storage.delete_file.call_count == 5


@pytest.mark.asyncio
async def test_delete_account_clerk_api(db: Session):
    """Mock httpx, verify Clerk delete API called with correct user ID."""
    user = _create_user(db)
    storage = _mock_storage()

    with patch("app.services.account_service.httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.delete = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        result = await AccountService.delete_account(
            user.id, db, storage, clerk_secret_key="sk_test_123"
        )

    assert result["clerk_deleted"] is True
    mock_client.delete.assert_called_once()
    call_url = mock_client.delete.call_args[0][0]
    assert user.clerk_user_id.replace("clerk_", "") in call_url or "clerk_" in call_url


@pytest.mark.asyncio
async def test_delete_account_clerk_failure(db: Session):
    """Clerk API fails, verify deletion still completes (best-effort)."""
    user = _create_user(db)
    user_id = user.id
    storage = _mock_storage()

    with patch("app.services.account_service.httpx.AsyncClient") as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_client.delete = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        result = await AccountService.delete_account(
            user_id, db, storage, clerk_secret_key="sk_test_123"
        )

    assert result["clerk_deleted"] is False
    # User should still be deleted from DB
    assert db.query(User).filter(User.id == user_id).first() is None


@pytest.mark.asyncio
async def test_delete_account_cancels_sync_jobs(db: Session):
    """Verify in-flight sync_queue items are cancelled before deletion."""
    user = _create_user(db)

    # Create sync queue items
    for sq_status in ["pending", "processing", "completed", "failed"]:
        sq = SyncQueue(
            user_id=user.id,
            item_type="page_text",
            item_id="item-1",
            content_hash="hash-1",
            target_name="notion",
            status=sq_status,
        )
        db.add(sq)
    db.commit()

    # Verify we have 2 pending/processing items initially
    active_before = (
        db.query(SyncQueue)
        .filter(SyncQueue.user_id == user.id, SyncQueue.status.in_(["pending", "processing"]))
        .count()
    )
    assert active_before == 2

    storage = _mock_storage()
    await AccountService.delete_account(user.id, db, storage)

    # After deletion, remaining queue items (if any from SQLite not cascading)
    # should have been cancelled before the user was deleted
    remaining = db.query(SyncQueue).filter(SyncQueue.user_id == user.id).all()
    for sq in remaining:
        # The pending/processing items should have been cancelled
        assert sq.status in ("cancelled", "completed", "failed")


@pytest.mark.asyncio
async def test_delete_account_no_clerk_key(db: Session):
    """Without clerk_secret_key, Clerk deletion is skipped."""
    user = _create_user(db)
    storage = _mock_storage()

    result = await AccountService.delete_account(user.id, db, storage, clerk_secret_key=None)

    assert result["clerk_deleted"] is False


@pytest.mark.asyncio
async def test_delete_account_user_not_found(db: Session):
    """Deleting non-existent user raises ValueError."""
    storage = _mock_storage()
    with pytest.raises(ValueError, match="User not found"):
        await AccountService.delete_account(99999, db, storage)
