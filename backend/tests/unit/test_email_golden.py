"""Golden-file tests for every email EmailService sends.

Each case calls one ``send_*`` method with fixed inputs and compares exactly
what would be handed to Resend (from, to, subject, html) with the files in
``tests/fixtures/email_golden/``. Inputs include HTML special characters so
escaping is covered too.

To regenerate after an intended change to an email:
    UPDATE_EMAIL_GOLDEN=1 pytest tests/unit/test_email_golden.py
and review the diff of the fixture files.
"""

import json
import os
from pathlib import Path

import pytest

from app.utils import email as email_module
from app.utils.email import EmailService

GOLDEN_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "email_golden"
UPDATE = os.environ.get("UPDATE_EMAIL_GOLDEN") == "1"

NAME = 'Ann <b>O\'Neil</b> & "Co"'

CASES = {
    "welcome": ("send_welcome_email", {"user_email": "ann@example.com", "user_name": NAME}),
    "sync_notification": (
        "send_sync_notification",
        {"user_email": "ann@example.com", "user_name": NAME, "notebook_count": 3},
    ),
    "admin_alert_warning": (
        "send_admin_alert",
        {"subject": "Disk <full>\nX", "message": "line 1\n<script>x</script> & more",
         "severity": "warning"},
    ),
    "admin_alert_unknown_severity": (
        "send_admin_alert",
        {"subject": "Plain", "message": "msg", "severity": "other"},
    ),
    "admin_alert_default": ("send_admin_alert", {"subject": "Info", "message": "ok"}),
    "invite_approved": (
        "send_invite_approved_email",
        {"email": "bo@example.com", "name": "Bo & Co",
         "invite_link": "https://app.example.com/sign-up?invite=a&b=<c>"},
    ),
    "invite_approved_no_name": (
        "send_invite_approved_email",
        {"email": "bo@example.com", "name": None, "invite_link": "https://app.example.com/i"},
    ),
    "waitlist_notification": (
        "send_waitlist_notification_email",
        {"email": "new<user>@example.com", "name": NAME},
    ),
    "waitlist_notification_no_name": (
        "send_waitlist_notification_email",
        {"email": "new@example.com", "name": None},
    ),
    "quota_warning": (
        "send_quota_warning_email",
        {"user_email": "ann@example.com", "user_name": NAME, "used": 27, "limit": 30,
         "percentage": 90.0, "reset_at": "February 1, 2026"},
    ),
    "quota_warning_fractional": (
        "send_quota_warning_email",
        {"user_email": "ann@example.com", "user_name": NAME, "used": 175, "limit": 200,
         "percentage": 87.5, "reset_at": "<soon>"},
    ),
    "quota_exceeded": (
        "send_quota_exceeded_email",
        {"user_email": "ann@example.com", "user_name": NAME, "limit": 30,
         "reset_at": "February 1, 2026"},
    ),
    "agent_nudge": ("send_agent_nudge_email", {"user_email": "ann@example.com", "user_name": NAME}),
    "first_sync_celebration": (
        "send_first_sync_celebration_email",
        {"user_email": "ann@example.com", "user_name": NAME, "notebook_count": 4,
         "page_count": 52},
    ),
    "first_ocr_celebration": (
        "send_first_ocr_celebration_email",
        {"user_email": "ann@example.com", "user_name": NAME,
         "ocr_snippet": "Buy <milk> & \"eggs\""},
    ),
    "first_ocr_celebration_no_snippet": (
        "send_first_ocr_celebration_email",
        {"user_email": "ann@example.com", "user_name": NAME},
    ),
    "notion_nudge": ("send_notion_nudge_email", {"user_email": "ann@example.com", "user_name": NAME}),
    "feedback_request": (
        "send_feedback_request_email", {"user_email": "ann@example.com", "user_name": NAME}
    ),
}


def test_every_public_send_method_has_a_case():
    methods = {
        name for name in vars(EmailService)
        if name.startswith("send_") and name != "send_email"
    }
    assert methods == {method for method, _ in CASES.values()}


@pytest.fixture
def sent(monkeypatch):
    """Capture the params EmailService hands to Resend."""
    calls = []
    monkeypatch.setattr(email_module.settings, "resend_api_key", "re_test_key")
    monkeypatch.setattr(email_module.settings, "resend_from_email", "noreply@example.com")
    monkeypatch.setattr(email_module.settings, "resend_from_name", "rMirror Cloud")
    monkeypatch.setattr(email_module.settings, "admin_email", "admin@example.com")
    monkeypatch.setattr(email_module.settings, "dashboard_url", "https://dash.example.com")
    monkeypatch.setattr(email_module.resend, "api_key", None)

    def fake_send(params):
        calls.append(params)
        return {"id": "test"}

    monkeypatch.setattr(email_module.resend.Emails, "send", staticmethod(fake_send))
    return calls


@pytest.mark.parametrize("case", sorted(CASES))
def test_email_matches_golden(case, sent):
    method, kwargs = CASES[case]
    assert getattr(EmailService(), method)(**kwargs) is True
    assert len(sent) == 1
    params = dict(sent[0])
    html = params.pop("html")

    html_file = GOLDEN_DIR / f"{case}.html"
    meta_file = GOLDEN_DIR / f"{case}.json"
    if UPDATE:
        GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
        html_file.write_bytes(html.encode("utf-8"))
        meta_file.write_text(
            json.dumps(params, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    assert html == html_file.read_bytes().decode("utf-8")
    assert params == json.loads(meta_file.read_text(encoding="utf-8"))
