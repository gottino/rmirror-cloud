"""Tests for the public waitlist endpoint and its emails."""

from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.waitlist import WaitlistEntry
from app.config import get_settings
from app.database import get_db
from app.utils.email import EmailService, _clean_subject


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    from app.main import app

    def _get_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def admin_email(monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_email", "admin@example.com")
    monkeypatch.setattr("app.utils.email.settings.admin_email", "admin@example.com")
    return "admin@example.com"


def test_new_and_existing_email_get_identical_response(client, db, admin_email):
    body = {"email": "same-answer@example.com", "name": "Ada"}
    with patch("app.utils.email.get_email_service"):
        first = client.post("/v1/waitlist", json=body)
        second = client.post("/v1/waitlist", json=body)
        other_name = client.post(
            "/v1/waitlist", json={"email": "same-answer@example.com", "name": "Bob"}
        )
    assert first.status_code == second.status_code == other_name.status_code == 202
    assert first.content == second.content == other_name.content
    assert set(first.json()) == {"status", "message"}
    assert db.query(WaitlistEntry).count() == 1


def test_admin_notification_sent_only_for_new_signup(client, admin_email):
    service = MagicMock()
    with patch("app.utils.email.get_email_service", return_value=service):
        client.post("/v1/waitlist", json={"email": "once@example.com", "name": "N"})
        client.post("/v1/waitlist", json={"email": "once@example.com", "name": "N"})
    service.send_waitlist_notification_email.assert_called_once_with(
        email="once@example.com", name="N"
    )


def test_email_failure_does_not_fail_signup(client, db, admin_email):
    service = MagicMock()
    service.send_waitlist_notification_email.side_effect = RuntimeError("resend down")
    with patch("app.utils.email.get_email_service", return_value=service):
        resp = client.post("/v1/waitlist", json={"email": "boom@example.com"})
    assert resp.status_code == 202
    assert db.query(WaitlistEntry).filter_by(email="boom@example.com").count() == 1


def test_notification_skipped_without_admin_email(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "admin_email", None)
    service = MagicMock()
    with patch("app.utils.email.get_email_service", return_value=service):
        resp = client.post("/v1/waitlist", json={"email": "noadmin@example.com"})
    assert resp.status_code == 202
    service.send_waitlist_notification_email.assert_not_called()


def _capture_send(monkeypatch):
    service = EmailService()
    sent = {}

    def fake_send(self, to_email, subject, html_content, **kw):
        sent.update(to=to_email, subject=subject, html=html_content, kw=kw)
        return True

    monkeypatch.setattr(EmailService, "send_email", fake_send)
    return service, sent


def test_waitlist_notification_escapes_and_uses_admin_email(monkeypatch, admin_email):
    service, sent = _capture_send(monkeypatch)
    service.send_waitlist_notification_email(
        email="x@example.com", name='<a href="https://evil.example">hi</a>'
    )
    assert sent["to"] == admin_email
    assert '<a href="https://evil.example">' not in sent["html"]
    assert "&lt;a href=&quot;https://evil.example&quot;&gt;" in sent["html"]


def test_waitlist_notification_subject_has_no_newlines(monkeypatch, admin_email):
    service, sent = _capture_send(monkeypatch)
    service.send_waitlist_notification_email(email="a@example.com\r\nBcc: x", name=None)
    assert "\r" not in sent["subject"] and "\n" not in sent["subject"]


def test_waitlist_notification_not_sent_without_admin_email(monkeypatch):
    monkeypatch.setattr("app.utils.email.settings.admin_email", None)
    service, sent = _capture_send(monkeypatch)
    assert service.send_waitlist_notification_email("a@example.com", "A") is False
    assert sent == {}


def test_invite_and_user_emails_escape_names(monkeypatch):
    service, sent = _capture_send(monkeypatch)
    evil = "<script>alert(1)</script>"
    service.send_invite_approved_email("a@example.com", evil, 'x"><b>')
    assert evil not in sent["html"] and '"><b>' not in sent["html"]
    service.send_welcome_email("a@example.com", evil)
    assert evil not in sent["html"]
    service.send_sync_notification("a@example.com", evil, 1)
    assert evil not in sent["html"]
    service.send_first_ocr_celebration_email("a@example.com", evil, ocr_snippet=evil)
    assert evil not in sent["html"]
    service.send_admin_alert("<b>subj</b>\nx", "<i>msg</i>", "info")
    assert "<b>subj</b>" not in sent["html"] and "<i>msg</i>" not in sent["html"]
    assert "\n" not in sent["subject"]


def test_clean_subject_strips_line_breaks():
    assert _clean_subject("a\r\nb\nc") == "a b c"
