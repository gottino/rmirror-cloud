"""Uploads are size-limited while being read; request models are bounded."""

import io
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient

from app.api.sync import MAX_METADATA_NOTEBOOKS, MAX_PAGES_PER_NOTEBOOK
from app.auth.clerk import get_clerk_active_user
from app.config import get_settings
from app.dependencies import get_storage_service
from app.models.notebook import DocumentType, Notebook
from app.models.user import User
from app.utils.files import read_upload_limited
from tests.test_config import test_app  # noqa: F401,F811 - fixture

PAGE_UUID = "0b6d1f9e-2c55-4a39-9f5e-1d2b3c4d5e6f"
NB_UUID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
API = "/v1"
OCTET = "application/octet-stream"


@pytest.fixture
def storage():
    fake = AsyncMock()
    fake.upload_file.return_value = "stored-key"
    return fake


@pytest.fixture
def client_user(db, test_app, reset_rate_limiter, storage, monkeypatch):  # noqa: F811
    user = User(email="limits@example.com", clerk_user_id="clerk_limits")
    db.add(user)
    db.commit()
    db.refresh(user)

    async def _user():
        return user

    settings = get_settings()
    monkeypatch.setattr(settings, "max_rm_file_size", 100)
    monkeypatch.setattr(settings, "max_metadata_file_size", 50)
    monkeypatch.setattr(settings, "max_upload_size", 200)

    test_app.dependency_overrides[get_clerk_active_user] = _user
    test_app.dependency_overrides[get_storage_service] = lambda: storage
    with TestClient(test_app) as client:
        yield client, user
    test_app.dependency_overrides.pop(get_clerk_active_user, None)
    test_app.dependency_overrides.pop(get_storage_service, None)


# --- helper -----------------------------------------------------------------


class _CountingFile:
    """Stands in for a spooled upload and records how much was read."""

    size = None

    def __init__(self, total):
        self.remaining = total
        self.read_bytes = 0

    async def read(self, n=-1):
        n = self.remaining if n < 0 else min(n, self.remaining)
        self.remaining -= n
        self.read_bytes += n
        return b"x" * n


@pytest.mark.asyncio
async def test_helper_stops_reading_soon_after_limit():
    from fastapi import HTTPException

    f = _CountingFile(10 * 1024 * 1024)
    with pytest.raises(HTTPException) as exc:
        await read_upload_limited(f, 1000, "thing")
    assert exc.value.status_code == 413
    assert f.read_bytes <= 1000 + 64 * 1024


@pytest.mark.asyncio
async def test_helper_rejects_known_size_without_reading():
    from fastapi import HTTPException

    f = _CountingFile(10)
    f.size = 5000
    with pytest.raises(HTTPException) as exc:
        await read_upload_limited(f, 1000, "thing")
    assert exc.value.status_code == 413
    assert f.read_bytes == 0


@pytest.mark.asyncio
async def test_helper_returns_content_at_limit():
    up = UploadFile(file=io.BytesIO(b"a" * 1000), filename="a.bin")
    assert await read_upload_limited(up, 1000, "thing") == b"a" * 1000


# --- .rm / .metadata / .content ---------------------------------------------


def test_oversized_rm_rejected_and_nothing_converted(client_user):
    client, _ = client_user
    with patch("app.api.processing.RMConverter") as converter, patch(
        "app.api.processing.OCRService"
    ) as ocr:
        resp = client.post(
            f"{API}/processing/rm-file",
            files={"rm_file": (f"{PAGE_UUID}.rm", io.BytesIO(b"x" * 101), OCTET)},
        )
    assert resp.status_code == 413
    converter.assert_not_called()
    ocr.assert_not_called()


def test_oversized_metadata_rejected(client_user):
    client, _ = client_user
    with patch("app.api.processing.RMConverter") as converter:
        resp = client.post(
            f"{API}/processing/rm-file",
            files={
                "rm_file": (f"{PAGE_UUID}.rm", io.BytesIO(b"x"), OCTET),
                "metadata_file": (
                    f"{NB_UUID}.metadata",
                    io.BytesIO(b" " * 51),
                    "application/json",
                ),
            },
        )
    assert resp.status_code == 413
    converter.assert_not_called()


def test_oversized_content_rejected(client_user, db):
    client, user = client_user
    db.add(
        Notebook(
            user_id=user.id,
            notebook_uuid=NB_UUID,
            visible_name="n",
            document_type=DocumentType.NOTEBOOK,
        )
    )
    db.commit()
    resp = client.post(
        f"{API}/notebooks/{NB_UUID}/content",
        files={"content_file": ("x.content", io.BytesIO(b" " * 51), "application/json")},
    )
    assert resp.status_code == 413


def test_content_within_limit_still_works(client_user, db):
    client, user = client_user
    db.add(
        Notebook(
            user_id=user.id,
            notebook_uuid=NB_UUID,
            visible_name="n",
            document_type=DocumentType.NOTEBOOK,
        )
    )
    db.commit()
    resp = client.post(
        f"{API}/notebooks/{NB_UUID}/content",
        files={"content_file": ("x.content", io.BytesIO(b'{"pages": []}'), "application/json")},
    )
    assert resp.status_code == 200, resp.text


# --- POST /notebooks/upload -------------------------------------------------


def test_upload_rejects_disallowed_type(client_user, storage):
    client, _ = client_user
    resp = client.post(
        f"{API}/notebooks/upload",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert resp.status_code == 400
    storage.upload_file.assert_not_called()


def test_upload_rejects_oversized_document(client_user, storage):
    client, _ = client_user
    resp = client.post(
        f"{API}/notebooks/upload",
        files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4" + b"x" * 300), "application/pdf")},
    )
    assert resp.status_code == 413
    storage.upload_file.assert_not_called()


def test_upload_pdf_still_works(client_user, storage):
    client, _ = client_user
    resp = client.post(
        f"{API}/notebooks/upload",
        files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4 small"), "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    storage.upload_file.assert_awaited_once()


# --- metadata sync request bounds -------------------------------------------


def _nb(i, pages=()):
    return {"uuid": f"{i:08x}-0000-4000-8000-000000000000", "visible_name": "n", "pages": list(pages)}


def test_too_many_notebooks_is_422(client_user):
    client, _ = client_user
    body = {"notebooks": [_nb(i) for i in range(MAX_METADATA_NOTEBOOKS + 1)]}
    assert client.post(f"{API}/sync/metadata", json=body).status_code == 422


def test_too_many_pages_is_422(client_user):
    client, _ = client_user
    pages = [PAGE_UUID] * (MAX_PAGES_PER_NOTEBOOK + 1)
    body = {"notebooks": [_nb(1, pages)]}
    assert client.post(f"{API}/sync/metadata", json=body).status_code == 422


def test_normal_metadata_sync_still_works(client_user):
    client, _ = client_user
    body = {"notebooks": [_nb(1, [PAGE_UUID])]}
    resp = client.post(f"{API}/sync/metadata", json=body)
    assert resp.status_code == 200, resp.text
