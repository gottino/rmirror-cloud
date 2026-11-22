"""A page with OCR text always comes back with a complete, readable PDF.

Regression test for staging, where every page PDF reached the browser as its
first line (9 bytes) and the dashboard viewer stayed empty while OCR text
showed fine. The stored files were complete; the rate-limit middleware cut
the streamed response off after the first chunk.

These tests run against ``app.main.app``, the production app with its full
middleware stack (rate limiting, CORS, security headers, request context).
The usual test app (``tests.test_config``) has no middleware, which is why
the earlier tests passed. Only the database, storage, auth and the OCR
provider are replaced.
"""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.auth.clerk import get_clerk_active_user, get_clerk_session_user
from app.core.pdf_service import PDFService
from app.core.rm_converter import RMConverter
from app.database import get_db
from app.dependencies import get_storage_service
from app.main import app as production_app
from app.models.notebook_page import NotebookPage
from app.models.page import Page
from tests.conftest import create_user_with_quota
from tests.unit.test_request_level_risky_paths import FIXTURES, PAGE_UUID, _upload_page

OCR_TEXT = "Shopping list\n- [ ] buy milk\n- [ ] call the plumber"

# A real, multi-object PDF, like rsvg-convert produces: many lines, so a
# streamed response is sent in many chunks.
PAGE_PDF = PDFService.create_placeholder_pdf("handwritten page " * 3)


def _assert_complete_pdf(body: bytes, expected: bytes | None = None) -> PdfReader:
    assert body.startswith(b"%PDF-"), body[:20]
    assert body.rstrip().endswith(b"%%EOF"), body[-20:]
    if expected is not None:
        assert len(body) == len(expected), f"got {len(body)} of {len(expected)} bytes"
        assert body == expected
    reader = PdfReader(io.BytesIO(body))
    assert len(reader.pages) >= 1
    return reader


@pytest.fixture
def prod_client(db):
    """(client, storage) for the production app; storage keeps files in memory."""
    user = create_user_with_quota(db, email="pdf-roundtrip@example.com", used=0, limit=30)
    user.clerk_user_id = "clerk_pdf_roundtrip"
    db.commit()

    stored: dict[str, bytes] = {}
    storage = MagicMock()

    async def _upload(stream, key, content_type=None):
        stored[key] = stream.read()

    async def _download(key):
        return stored[key]

    async def _exists(key):
        return key in stored

    storage.upload_file = AsyncMock(side_effect=_upload)
    storage.download_file = AsyncMock(side_effect=_download)
    storage.file_exists = AsyncMock(side_effect=_exists)
    storage.stored = stored

    async def _user():
        return user

    def _db():
        yield db

    overrides = {
        get_db: _db,
        get_storage_service: lambda: storage,
        get_clerk_active_user: _user,
        get_clerk_session_user: _user,
    }
    production_app.dependency_overrides.update(overrides)
    # No ``with``: the lifespan (sync worker, schedulers) does not start.
    client = TestClient(production_app)
    try:
        with patch("app.services.quota_service.get_email_service"):
            yield client, storage
    finally:
        for dep in overrides:
            production_app.dependency_overrides.pop(dep, None)


@pytest.fixture
def uploaded_page(db, prod_client):
    """Upload a real .rm page with OCR returning text; returns (client, storage, page)."""
    client, storage = prod_client
    ocr = MagicMock()
    ocr.extract_text_from_pdf = AsyncMock(return_value=OCR_TEXT)
    with patch.object(RMConverter, "svg_to_pdf_bytes", lambda self, svg: PAGE_PDF), patch(
        "app.api.processing.OCRService", return_value=ocr
    ):
        resp = _upload_page(client, (FIXTURES / "page_1.rm").read_bytes())
    assert resp.status_code == 200, resp.text
    db.expire_all()
    page = db.query(Page).filter_by(page_uuid=PAGE_UUID).one()
    # Page order normally comes from the notebook's .content file (not uploaded
    # here); exports list pages through this mapping.
    if not db.query(NotebookPage).filter_by(page_id=page.id).first():
        db.add(NotebookPage(notebook_id=page.notebook_id, page_id=page.id, page_number=1))
        db.commit()
    return client, storage, page


def test_page_with_ocr_text_has_a_complete_pdf(uploaded_page):
    client, storage, page = uploaded_page
    assert page.ocr_text and page.ocr_text.strip(), "precondition: OCR text is stored"
    assert page.pdf_s3_key, "a page with OCR text must have a PDF"
    _assert_complete_pdf(storage.stored[page.pdf_s3_key], PAGE_PDF)

    resp = client.get(f"/v1/pages/{page.id}/pdf")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    _assert_complete_pdf(resp.content, PAGE_PDF)


def test_notebook_pdf_export_is_complete(uploaded_page):
    client, _, page = uploaded_page

    resp = client.get(f"/v1/notebooks/{page.notebook_id}/export", params={"format": "pdf"})

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/pdf")
    _assert_complete_pdf(resp.content)


def test_notebook_markdown_export_contains_the_ocr_text(uploaded_page):
    client, _, page = uploaded_page

    resp = client.get(f"/v1/notebooks/{page.notebook_id}/export", params={"format": "markdown"})

    assert resp.status_code == 200, resp.text
    assert "call the plumber" in resp.text
