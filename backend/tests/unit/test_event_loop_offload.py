"""Blocking third-party calls must not stall the event loop.

Request handlers and the sync worker share one event loop per uvicorn
process. Each test below makes the third-party client block with
``time.sleep`` and runs a ticker coroutine alongside the call. If the call ran
on the loop, the ticker could not run until it finished; when it is offloaded
to a thread, the ticker keeps ticking.
"""

import asyncio
import io
import time
from unittest.mock import MagicMock, patch

import pytest

from tests.test_config import test_app  # noqa: F401 - fixture

BLOCK_SECONDS = 0.3
TICK_SECONDS = 0.02
# Running on the loop gives the ticker 0-1 ticks; offloaded gives about 15.
MIN_TICKS = 5


async def _ticks_while(coro) -> tuple[object, int]:
    """Await ``coro`` while counting how often another coroutine gets to run."""
    ticks = 0
    done = asyncio.Event()

    async def ticker():
        nonlocal ticks
        while not done.is_set():
            await asyncio.sleep(TICK_SECONDS)
            ticks += 1

    task = asyncio.create_task(ticker())
    try:
        result = await coro
    finally:
        done.set()
        await task
    return result, ticks


def _slow(return_value=None):
    def call(*args, **kwargs):
        time.sleep(BLOCK_SECONDS)
        return return_value

    return call


# ---------------------------------------------------------------------------
# run_off_loop helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_off_loop_keeps_loop_responsive_and_returns_value():
    from app.utils.concurrency import run_off_loop

    @run_off_loop
    async def blocking(x):
        time.sleep(BLOCK_SECONDS)
        return x * 2

    result, ticks = await _ticks_while(blocking(21))
    assert result == 42
    assert ticks >= MIN_TICKS


@pytest.mark.asyncio
async def test_run_off_loop_propagates_exceptions():
    from app.utils.concurrency import run_off_loop

    @run_off_loop
    async def boom():
        raise ValueError("from the worker thread")

    with pytest.raises(ValueError, match="from the worker thread"):
        await boom()


@pytest.mark.asyncio
async def test_run_off_loop_supports_nested_calls():
    from app.utils.concurrency import run_off_loop

    @run_off_loop
    async def inner():
        time.sleep(0.01)
        return "inner"

    @run_off_loop
    async def outer():
        return await inner() + "+outer"

    assert await outer() == "inner+outer"


# ---------------------------------------------------------------------------
# OCR (Gemini SDK is synchronous)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ocr_does_not_block_event_loop():
    from app.core.ocr_service import OCRService

    response = MagicMock()
    response.text = "hello from the page"
    response.usage_metadata = None

    with patch("app.core.ocr_service.genai.Client") as client_cls:
        client_cls.return_value.models.generate_content.side_effect = _slow(response)
        service = OCRService(api_key="test-key")
        text, ticks = await _ticks_while(service.extract_text_from_pdf(b"%PDF-1.4"))

    assert text == "hello from the page"
    assert ticks >= MIN_TICKS


# ---------------------------------------------------------------------------
# S3 / B2 storage (boto3 is synchronous)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_s3_upload_and_download_do_not_block_event_loop():
    with patch("app.storage.s3.boto3.client") as client_factory:
        s3 = client_factory.return_value
        s3.upload_fileobj.side_effect = _slow()
        body = MagicMock()
        body.read.return_value = b"pdf-bytes"
        s3.get_object.side_effect = _slow({"Body": body})

        from app.storage.s3 import S3StorageService

        storage = S3StorageService()

        key, upload_ticks = await _ticks_while(
            storage.upload_file(io.BytesIO(b"x"), "users/1/a.pdf", "application/pdf")
        )
        data, download_ticks = await _ticks_while(storage.download_file("users/1/a.pdf"))

    assert key == "users/1/a.pdf"
    assert data == b"pdf-bytes"
    assert upload_ticks >= MIN_TICKS
    assert download_ticks >= MIN_TICKS


@pytest.mark.asyncio
async def test_s3_missing_key_still_raises_file_not_found():
    from botocore.exceptions import ClientError

    with patch("app.storage.s3.boto3.client") as client_factory:
        client_factory.return_value.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject"
        )
        from app.storage.s3 import S3StorageService

        with pytest.raises(FileNotFoundError):
            await S3StorageService().download_file("users/1/missing.pdf")


# ---------------------------------------------------------------------------
# Notion (notion_client.Client is synchronous)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notion_target_does_not_block_event_loop():
    with patch("app.integrations.notion_sync.NotionClient") as client_cls:
        client_cls.return_value.databases.retrieve.side_effect = _slow({"id": "db"})

        from app.integrations.notion_sync import NotionSyncTarget

        target = NotionSyncTarget(access_token="secret", database_id="db")
        ok, ticks = await _ticks_while(target.validate_connection())

    assert ok is True
    assert ticks >= MIN_TICKS


@pytest.mark.asyncio
async def test_notion_todos_target_does_not_block_event_loop():
    with patch("app.integrations.notion_todos_sync.NotionClient") as client_cls:
        client_cls.return_value.databases.retrieve.side_effect = _slow({"id": "db"})

        from app.integrations.notion_todos_sync import NotionTodosSyncTarget

        target = NotionTodosSyncTarget(access_token="secret", database_id="db")
        ok, ticks = await _ticks_while(target.validate_connection())

    assert ok is True
    assert ticks >= MIN_TICKS


@pytest.mark.asyncio
async def test_notion_oauth_service_does_not_block_event_loop():
    from app.services.notion_oauth import NotionOAuthService

    with patch("app.services.notion_oauth.NotionClient") as client_cls:
        client_cls.return_value.search.side_effect = _slow({"results": []})
        service = NotionOAuthService()
        databases, ticks = await _ticks_while(service.list_databases("secret"))

    assert databases == []
    assert ticks >= MIN_TICKS


# ---------------------------------------------------------------------------
# End to end: the API keeps answering while an upload is in OCR
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_answers_other_requests_while_upload_runs_ocr(db, test_app):
    """A slow Gemini call inside /processing/rm-file must not freeze the app.

    Only the external clients are faked: Gemini blocks for ``BLOCK_SECONDS``
    and the .rm converter blocks for a shorter time. The real OCRService and
    route code run. While the upload is in flight, a second request is sent;
    it must complete well before the upload does.
    """
    import httpx

    from app.auth.clerk import get_clerk_active_user
    from tests.conftest import create_user_with_quota

    user = create_user_with_quota(db, used=0, limit=30)

    async def as_user():
        return user

    test_app.dependency_overrides[get_clerk_active_user] = as_user

    @test_app.get("/__ping")
    async def ping():
        return {"ok": True}

    response = MagicMock()
    response.text = "page text"
    response.usage_metadata = None

    storage = MagicMock()

    async def store(*args, **kwargs):
        return "key"

    storage.upload_file.side_effect = store

    with patch("app.core.ocr_service.genai.Client") as genai_client, \
         patch("app.api.processing.get_storage_service", return_value=storage), \
         patch("app.api.processing.RMConverter") as converter_cls, \
         patch("app.core.ocr_service.settings.google_ai_api_key", "test-key"):
        genai_client.return_value.models.generate_content.side_effect = _slow(response)
        converter = converter_cls.return_value
        converter.has_content.return_value = True
        converter.rm_to_pdf_bytes.side_effect = lambda path: (time.sleep(0.05), b"%PDF")[1]

        transport = httpx.ASGITransport(app=test_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            started = time.monotonic()
            upload = asyncio.create_task(
                client.post(
                    "/v1/processing/rm-file",
                    files={
                        "rm_file": (
                            "0b6d1f9e-2c55-4a39-9f5e-1d2b3c4d5e6f.rm",
                            io.BytesIO(b"rm-bytes"),
                            "application/octet-stream",
                        )
                    },
                )
            )
            await asyncio.sleep(0.1)  # let the upload reach the OCR call
            ping_resp = await client.get("/__ping")
            ping_done = time.monotonic() - started
            upload_resp = await upload
            upload_done = time.monotonic() - started

    test_app.dependency_overrides.pop(get_clerk_active_user, None)

    assert ping_resp.status_code == 200
    assert upload_resp.status_code == 200, upload_resp.text
    assert upload_resp.json()["extracted_text"] == "page text"
    # The ping finished while Gemini was still "working".
    assert ping_done < upload_done - 0.1, (ping_done, upload_done)
