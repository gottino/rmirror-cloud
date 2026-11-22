"""Two failure modes that must degrade instead of returning HTTP 500.

1. The OCR provider fails during ``POST /processing/rm-file`` (billing, auth,
   quota, timeout, network): the upload still succeeds, the page is stored as
   ``pending_retry`` and the sync worker's catch-up sweep retries it with a
   bounded backoff. Provider text never reaches the client.
2. Stored integration credentials cannot be decrypted with this server's key:
   status endpoints answer 200 with ``needs_reconnect``, and the sync worker
   fails the item for good with a clear reason.
"""

import logging
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.auth.clerk import get_clerk_active_user, get_clerk_session_user
from app.core.rm_converter import RMConverter
from app.jobs import process_pending_pages as job
from app.models.page import OcrStatus, Page
from app.models.quota_usage import QuotaType, QuotaUsage
from app.models.sync_record import IntegrationConfig, SyncQueue
from app.services import encryption
from app.services.page_events import on_ocr_completed
from app.services.sync_worker import SyncWorker
from tests.conftest import create_user_with_quota
from tests.test_config import test_app  # noqa: F401 - fixture
from tests.unit.test_request_level_risky_paths import (  # noqa: F401 - fixture
    FIXTURES,
    PAGE_UUID,
    _upload_page,
    api,
)

API = "/v1"
PROVIDER_TEXT = "429 RESOURCE_EXHAUSTED: billing account acct-1234 has no credit left"


def _used(db, user_id):
    db.expire_all()
    return db.query(QuotaUsage).filter_by(user_id=user_id, quota_type=QuotaType.OCR).one().used


def _page(db):
    db.expire_all()
    return db.query(Page).filter_by(page_uuid=PAGE_UUID).one()


def _age(db, page_id, delta):
    """Move the page's last failure back by ``delta`` (as if time passed)."""
    db.query(Page).filter(Page.id == page_id).update(
        {Page.updated_at: datetime.utcnow() - delta}, synchronize_session=False
    )
    db.commit()


@pytest.fixture
def failing_upload(db, api):  # noqa: F811
    """Upload a real .rm page while the OCR provider raises; returns (resp, user, storage)."""
    client, user, storage = api
    ocr = MagicMock()
    ocr.extract_text_from_pdf = AsyncMock(side_effect=RuntimeError(PROVIDER_TEXT))
    with patch.object(RMConverter, "svg_to_pdf_bytes", lambda self, svg: b"%PDF-1.4 page"), patch(
        "app.api.processing.OCRService", return_value=ocr
    ):
        resp = _upload_page(client, (FIXTURES / "page_3.rm").read_bytes())
    ocr.extract_text_from_pdf.assert_awaited_once()
    return resp, user, storage


@pytest.fixture
def sweep(failing_upload):
    """Run one catch-up sweep with the given OCR result; downloads read the stored PDF."""
    _, _, storage = failing_upload

    async def _download(key):
        return storage.stored[key]

    job_storage = MagicMock()
    job_storage.download_file = AsyncMock(side_effect=_download)

    async def _run(db, ocr_result):
        ocr = MagicMock()
        ocr.extract_text_from_pdf = AsyncMock(side_effect=[ocr_result])
        with patch.object(job, "get_storage_service", return_value=job_storage), patch.object(
            job, "OCRService", return_value=ocr
        ), patch.object(job, "on_ocr_completed", wraps=on_ocr_completed) as hook:
            processed, _ = await job.process_pending_quota_pages(db)
        return processed, ocr.extract_text_from_pdf.await_count, hook.call_count

    return _run


# ---------------------------------------------------------------------------
# 1. OCR provider failure
# ---------------------------------------------------------------------------


def test_upload_with_failing_ocr_succeeds_and_stores_the_page(db, failing_upload):
    resp, user, storage = failing_upload

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["extracted_text"] == ""
    assert body["ocr_status"] == "pending_retry"
    assert body["page_count"] == 1 and body["page_id"] is not None
    # Nothing of the provider's error reaches the client
    assert "RESOURCE_EXHAUSTED" not in resp.text and "acct-1234" not in resp.text

    base = f"users/{user.id}/notebooks/"
    assert any(k.startswith(base) and k.endswith(f"{PAGE_UUID}.rm") for k in storage.stored)
    assert any(k.endswith(f"{PAGE_UUID}.pdf") for k in storage.stored)

    page = _page(db)
    assert page.id == body["page_id"]
    assert page.ocr_status == OcrStatus.PENDING_RETRY
    assert page.ocr_attempts == 1
    assert page.pdf_s3_key and page.s3_key
    assert "acct-1234" not in (page.ocr_error or "")
    # The reserved quota unit was given back
    assert _used(db, user.id) == 0


@pytest.mark.asyncio
async def test_catch_up_completes_the_page_once_ocr_works(db, failing_upload, sweep):
    _, user, _ = failing_upload
    page_id = _page(db).id

    # Not due yet: the sweep leaves it alone and calls no OCR
    assert await sweep(db, "never") == (0, 0, 0)
    assert _page(db).ocr_status == OcrStatus.PENDING_RETRY

    _age(db, page_id, job.ocr_retry_delay(1) + timedelta(seconds=1))
    processed, ocr_calls, hook_calls = await sweep(db, "recovered text")

    assert (processed, ocr_calls, hook_calls) == (1, 1, 1)
    page = _page(db)
    assert page.ocr_status == OcrStatus.COMPLETED
    assert page.ocr_text == "recovered text"
    assert page.ocr_attempts == 0 and page.ocr_error is None
    assert _used(db, user.id) == 1

    # Done: later sweeps do nothing
    assert await sweep(db, "again") == (0, 0, 0)


@pytest.mark.asyncio
async def test_retries_stop_after_the_bound(db, failing_upload, sweep):
    _, user, _ = failing_upload
    page_id = _page(db).id
    total_calls = 0

    for attempt in range(1, job.MAX_OCR_ATTEMPTS):
        _age(db, page_id, job.ocr_retry_delay(attempt) + timedelta(seconds=1))
        _, ocr_calls, hook_calls = await sweep(db, RuntimeError(PROVIDER_TEXT))
        total_calls += ocr_calls
        assert hook_calls == 0

    # One upload attempt + (MAX - 1) retries, then FAILED with a generic message
    assert total_calls == job.MAX_OCR_ATTEMPTS - 1
    page = _page(db)
    assert page.ocr_status == OcrStatus.FAILED
    assert page.ocr_attempts == job.MAX_OCR_ATTEMPTS
    assert page.ocr_error == job.OCR_GAVE_UP_MESSAGE
    assert _used(db, user.id) == 0

    # No more OCR calls, however much time passes
    _age(db, page_id, timedelta(days=365))
    assert await sweep(db, "never") == (0, 0, 0)


def test_retry_is_not_attempted_more_often_than_the_backoff(db, failing_upload):
    page = _page(db)
    now = datetime.utcnow()
    # Just after the failure: not due; after the first delay: due
    due = db.query(Page.id).filter(job.retry_due(now)).all()
    assert due == []
    due = db.query(Page.id).filter(job.retry_due(now + job.ocr_retry_delay(1))).all()
    assert [r[0] for r in due] == [page.id]
    assert job.ocr_retry_delay(2) == 2 * job.ocr_retry_delay(1)


def test_unexpected_upload_error_returns_no_internal_text(db, api):  # noqa: F811
    client, _, storage = api
    storage.upload_file.side_effect = RuntimeError("s3 says: secret-bucket-detail")
    ocr = MagicMock()
    ocr.extract_text_from_pdf = AsyncMock(return_value="text")
    with patch.object(RMConverter, "svg_to_pdf_bytes", lambda self, svg: b"%PDF"), patch(
        "app.api.processing.OCRService", return_value=ocr
    ):
        resp = _upload_page(client, (FIXTURES / "page_3.rm").read_bytes())
    assert resp.status_code == 500
    assert "secret-bucket-detail" not in resp.text


# ---------------------------------------------------------------------------
# 2. Undecryptable integration credentials
# ---------------------------------------------------------------------------


@pytest.fixture
def server_key(monkeypatch):
    """This server's INTEGRATION_MASTER_KEY (a fresh one per test)."""
    settings = MagicMock()
    settings.integration_master_key = Fernet.generate_key().decode()
    monkeypatch.setattr(encryption, "get_settings", lambda: settings)
    monkeypatch.setattr(encryption, "_encryption_service", None)
    yield
    encryption._encryption_service = None


def _foreign_ciphertext() -> str:
    """A config encrypted under another environment's key."""
    return Fernet(Fernet.generate_key()).encrypt(b'{"access_token": "t"}').decode()


@pytest.fixture
def dashboard(db, test_app, server_key, reset_rate_limiter):  # noqa: F811
    user = create_user_with_quota(db, email="reconnect@example.com")

    async def _user():
        return user

    test_app.dependency_overrides[get_clerk_active_user] = _user
    test_app.dependency_overrides[get_clerk_session_user] = _user
    with TestClient(test_app) as client:
        yield client, user


def _config(db, user, target, *, readable=False, enabled=True):
    config = IntegrationConfig(user_id=user.id, target_name=target, is_enabled=enabled)
    if readable:
        config.set_config({"access_token": "t", "database_id": "db", "project_name": "P"})
    else:
        config.config_encrypted = _foreign_ciphertext()
    db.add(config)
    db.commit()
    return config


def test_todoist_status_with_unreadable_credentials(db, dashboard, caplog):
    client, user = dashboard
    _config(db, user, "todoist")

    with caplog.at_level(logging.WARNING, logger="app.models.sync_record"):
        resp = client.get(f"{API}/integrations/todoist/status")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["connected"] is False
    assert body["needs_reconnect"] is True
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "todoist" in warnings[0] and str(user.id) in warnings[0]


def test_todoist_status_with_readable_credentials(db, dashboard):
    client, user = dashboard
    _config(db, user, "todoist", readable=True)

    body = client.get(f"{API}/integrations/todoist/status").json()
    assert body["connected"] is True and body["needs_reconnect"] is False
    assert body["project_name"] == "P"


@pytest.mark.parametrize("target", ["notion", "todoist", "notion-todos", "obsidian"])
def test_integrations_list_and_get_flag_unreadable_credentials(db, dashboard, target):
    client, user = dashboard
    _config(db, user, target)
    _config(db, user, "readwise", readable=True)

    resp = client.get(f"{API}/integrations/")
    assert resp.status_code == 200, resp.text
    flags = {i["target_name"]: i["needs_reconnect"] for i in resp.json()}
    assert flags == {target: True, "readwise": False}

    resp = client.get(f"{API}/integrations/{target}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["needs_reconnect"] is True


def test_todoist_reconnect_replaces_unreadable_credentials(db, dashboard):
    client, user = dashboard
    config = _config(db, user, "todoist")

    from app.api import todoist as todoist_api

    service = MagicMock()
    service.exchange_code_for_token = AsyncMock(return_value={"access_token": "new"})
    with patch.object(todoist_api, "TodoistOAuthService", return_value=service):
        state = todoist_api._create_oauth_state(user.id)
        resp = client.post(
            f"{API}/integrations/todoist/oauth/callback", json={"code": "c", "state": state}
        )

    assert resp.status_code == 200, resp.text
    db.expire_all()
    assert config.get_config() == {"access_token": "new"}
    assert config.is_enabled is False  # re-enabled once a project is chosen


@pytest.mark.asyncio
async def test_sync_worker_fails_item_with_unreadable_credentials(db, server_key):
    user = create_user_with_quota(db, email="worker-reconnect@example.com")
    config = _config(db, user, "notion")
    item = SyncQueue(
        user_id=user.id,
        item_type="page_text",
        item_id="1",
        content_hash="h",
        target_name="notion",
        status="processing",
    )
    db.add(item)
    db.commit()

    with patch("app.services.sync_worker.create_target") as create_target:
        await SyncWorker()._process_queue_item(db, item)

    create_target.assert_not_called()
    db.expire_all()
    assert item.status == "failed"
    assert "cannot be decrypted" in item.error_message
    assert "reconnect" in item.error_message
    assert config.config_encrypted not in item.error_message
