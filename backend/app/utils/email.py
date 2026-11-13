"""
Email utility using Resend for rMirror Cloud
"""

import logging
from functools import lru_cache
from html import escape as _e
from pathlib import Path
from string import Template
from typing import Optional

import resend

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# Email bodies live in app/templates/email/<name>.html as string.Template
# files: ``${name}`` is a placeholder and ``$$`` a literal dollar sign.
# Values are inserted as given, so callers escape them with ``_e`` first.
_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"


@lru_cache
def _template(name: str) -> Template:
    return Template((_TEMPLATE_DIR / f"{name}.html").read_text(encoding="utf-8"))


def _render(name: str, **values: object) -> str:
    """Fill the email template ``name`` with ``values`` (already escaped)."""
    return _template(name).substitute(values)


def _clean_subject(value: object) -> str:
    """Make a value safe for a plain-text subject line (no CR/LF)."""
    return " ".join(str(value).replace("\r", " ").replace("\n", " ").split())


class EmailService:
    """Service for sending emails via Resend"""

    def __init__(self):
        self.api_key = settings.resend_api_key
        self.from_email = settings.resend_from_email
        self.from_name = settings.resend_from_name

        if self.api_key:
            resend.api_key = self.api_key
        else:
            logger.warning("Resend API key not configured. Emails will not be sent.")

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        to_name: Optional[str] = None
    ) -> bool:
        """
        Send an email via Resend

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML content of email
            to_name: Recipient name (optional)

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.api_key:
            logger.error("Cannot send email: Resend API key not configured")
            return False

        try:
            # Build from field with name
            from_field = f"{self.from_name} <{self.from_email}>"

            # Build to field with name if provided
            to_field = (
                f"{_clean_subject(to_name)} <{to_email}>" if to_name else to_email
            )

            params = {
                "from": from_field,
                "to": [to_field],
                "subject": subject,
                "html": html_content,
            }

            response = resend.Emails.send(params)

            logger.info(f"Email sent successfully to {to_email} (ID: {response.get('id', 'unknown')})")
            return True

        except Exception as e:
            logger.error(f"Error sending email to {to_email}: {str(e)}")
            return False

    def send_welcome_email(self, user_email: str, user_name: str) -> bool:
        """Send welcome email to new user"""
        html_content = _render(
            "welcome",
            user_name=_e(user_name),
        )

        return self.send_email(
            to_email=user_email,
            subject="Welcome to rMirror Cloud",
            html_content=html_content,
            to_name=user_name
        )

    def send_sync_notification(
        self,
        user_email: str,
        user_name: str,
        notebook_count: int
    ) -> bool:
        """Send notification when notebooks are synced"""
        html_content = _render(
            "sync_notification",
            user_name=_e(user_name),
            notebook_count=notebook_count,
        )

        return self.send_email(
            to_email=user_email,
            subject=f"{notebook_count} Notebook(s) Synced",
            html_content=html_content,
            to_name=user_name
        )

    def send_admin_alert(
        self,
        subject: str,
        message: str,
        severity: str = "info"
    ) -> bool:
        """
        Send alert to admin

        Args:
            subject: Alert subject
            message: Alert message
            severity: info, warning, error, critical
        """
        # Updated color map to match design system
        color_map = {
            "info": "#7a9c89",      # sage-green (success)
            "warning": "#d4a574",   # amber-gold (secondary)
            "error": "#c85a54",     # terracotta (primary/accent)
            "critical": "#8b4049"   # status-error (subdued red)
        }

        emoji_map = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "critical": "🚨"
        }

        color = color_map.get(severity, "#7a9c89")
        emoji = emoji_map.get(severity, "ℹ️")

        html_content = _render(
            "admin_alert",
            color=_e(color),
            severity_upper=_e(severity.upper()),
            emoji=emoji,
            subject=_e(subject),
            message=_e(message),
        )

        return self.send_email(
            to_email=settings.admin_email,
            subject=f"[{_clean_subject(severity.upper())}] rMirror Cloud - {_clean_subject(subject)}",
            html_content=html_content
        )

    def send_invite_approved_email(
        self,
        email: str,
        name: Optional[str],
        invite_link: str,
    ) -> bool:
        """Send invite approval email with signup link."""
        display_name = name or "there"

        html_content = _render(
            "invite_approved",
            display_name=_e(display_name),
            invite_link=_e(invite_link),
        )

        return self.send_email(
            to_email=email,
            subject="You're in! Your rMirror Cloud invite is ready",
            html_content=html_content,
            to_name=name,
        )

    def send_waitlist_notification_email(
        self,
        email: str,
        name: Optional[str],
    ) -> bool:
        """Notify admin when someone joins the waitlist."""
        if not settings.admin_email:
            logger.info("ADMIN_EMAIL not set; skipping waitlist admin notification")
            return False

        display_name = name or "Not provided"
        admin_url = f"{settings.dashboard_url}/admin/waitlist"

        html_content = _render(
            "waitlist_notification",
            email=_e(email),
            display_name=_e(display_name),
            admin_url=_e(admin_url),
        )

        return self.send_email(
            to_email=settings.admin_email,
            subject=f"New waitlist signup: {_clean_subject(email)}",
            html_content=html_content,
        )

    def send_quota_warning_email(
        self,
        user_email: str,
        user_name: str,
        used: int,
        limit: int,
        percentage: float,
        reset_at: str
    ) -> bool:
        """Send warning email when quota approaching limit (80-90%)"""
        remaining = limit - used

        html_content = _render(
            "quota_warning",
            user_name=_e(user_name),
            used=used,
            limit=limit,
            percentage_rounded=format(percentage, ".0f"),
            remaining=remaining,
            percentage=percentage,
            reset_at=_e(reset_at),
        )

        return self.send_email(
            to_email=user_email,
            subject=f"⚠️ You've used {percentage:.0f}% of your monthly quota",
            html_content=html_content,
            to_name=user_name
        )

    def send_quota_exceeded_email(
        self,
        user_email: str,
        user_name: str,
        limit: int,
        reset_at: str
    ) -> bool:
        """Send notification email when quota exceeded (100%)"""

        html_content = _render(
            "quota_exceeded",
            user_name=_e(user_name),
            limit=limit,
            reset_at=_e(reset_at),
        )

        return self.send_email(
            to_email=user_email,
            subject=f"🔴 Monthly quota reached ({limit} pages used)",
            html_content=html_content,
            to_name=user_name
        )

    def send_agent_nudge_email(self, user_email: str, user_name: str) -> bool:
        """Send nudge email to users who haven't installed the agent yet (E3)"""

        html_content = _render(
            "agent_nudge",
            user_name=_e(user_name),
        )

        return self.send_email(
            to_email=user_email,
            subject="Your notebooks are waiting — set up in 5 minutes",
            html_content=html_content,
            to_name=user_name
        )

    def send_first_sync_celebration_email(
        self,
        user_email: str,
        user_name: str,
        notebook_count: int,
        page_count: int
    ) -> bool:
        """Send celebration email after first successful sync (E4)"""

        html_content = _render(
            "first_sync_celebration",
            user_name=_e(user_name),
            notebook_count=notebook_count,
            page_count=page_count,
        )

        return self.send_email(
            to_email=user_email,
            subject="Your notebooks are in the cloud!",
            html_content=html_content,
            to_name=user_name
        )

    def send_first_ocr_celebration_email(
        self,
        user_email: str,
        user_name: str,
        ocr_snippet: Optional[str] = None
    ) -> bool:
        """Send celebration email after first OCR completion (E5)"""

        # Build OCR snippet preview block if snippet is provided
        snippet_html = ""
        if ocr_snippet:
            snippet_html = _render(
                "first_ocr_celebration_snippet",
                ocr_snippet=_e(ocr_snippet),
            )

        html_content = _render(
            "first_ocr_celebration",
            user_name=_e(user_name),
            snippet_html=snippet_html,
        )

        return self.send_email(
            to_email=user_email,
            subject="Your handwriting is now searchable",
            html_content=html_content,
            to_name=user_name
        )

    def send_notion_nudge_email(self, user_email: str, user_name: str) -> bool:
        """Send nudge email to connect Notion integration (E6)"""

        html_content = _render(
            "notion_nudge",
            user_name=_e(user_name),
        )

        return self.send_email(
            to_email=user_email,
            subject="Your notes + Notion = magic",
            html_content=html_content,
            to_name=user_name
        )

    def send_feedback_request_email(self, user_email: str, user_name: str) -> bool:
        """Send feedback request email to gather user insights (E7)"""

        html_content = _render(
            "feedback_request",
            user_name=_e(user_name),
        )

        return self.send_email(
            to_email=user_email,
            subject="Quick question: how's rMirror working for you?",
            html_content=html_content,
            to_name=user_name
        )


# Singleton instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get or create EmailService singleton"""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
