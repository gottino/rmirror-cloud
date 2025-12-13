"""
Email utility using Resend for rMirror Cloud
"""

import logging
from typing import Optional, List
import resend
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


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
        plain_text_content: Optional[str] = None,
        to_name: Optional[str] = None
    ) -> bool:
        """
        Send an email via Resend

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML content of email
            plain_text_content: Plain text version (optional, not used by Resend)
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
            to_field = f"{to_name} <{to_email}>" if to_name else to_email

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
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h1 style="color: #6B46C1;">Welcome to rMirror Cloud!</h1>
                    <p>Hi {user_name},</p>
                    <p>Thank you for signing up for rMirror Cloud. We're excited to help you sync and transcribe your reMarkable notebooks.</p>
                    <h2 style="color: #6B46C1;">Getting Started</h2>
                    <p>To start syncing your reMarkable notebooks:</p>
                    <ol>
                        <li>Visit your <a href="https://rmirror.io" style="color: #6B46C1; text-decoration: none;">dashboard</a> to download the macOS agent</li>
                        <li>Install the agent and sign in with your account</li>
                        <li>Your notebooks will automatically sync to the cloud</li>
                    </ol>
                    <p style="margin-top: 30px;">
                        <a href="https://rmirror.io"
                           style="display: inline-block; padding: 12px 24px; background-color: #6B46C1; color: white; text-decoration: none; border-radius: 6px; font-weight: 600;">
                            Go to Dashboard
                        </a>
                    </p>
                    <p style="color: #6B7280; font-size: 14px; margin-top: 30px;">
                        If you have any questions, feel free to reach out to our support team.
                    </p>
                    <p style="margin-top: 30px;">
                        <strong>The rMirror Team</strong>
                    </p>
                </div>
            </body>
        </html>
        """

        plain_text = f"""
        Welcome to rMirror Cloud!

        Hi {user_name},

        Thank you for signing up for rMirror Cloud. We're excited to help you sync and transcribe your reMarkable notebooks.

        Getting Started:
        1. Visit your dashboard at https://rmirror.io to download the macOS agent
        2. Install the agent and sign in with your account
        3. Your notebooks will automatically sync to the cloud

        Go to Dashboard: https://rmirror.io

        If you have any questions, feel free to reach out to our support team.

        Happy note-taking!

        The rMirror Team
        """

        return self.send_email(
            to_email=user_email,
            subject="Welcome to rMirror Cloud",
            html_content=html_content,
            plain_text_content=plain_text,
            to_name=user_name
        )

    def send_sync_notification(
        self,
        user_email: str,
        user_name: str,
        notebook_count: int
    ) -> bool:
        """Send notification when notebooks are synced"""
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h1 style="color: #6B46C1;">Notebooks Synced Successfully</h1>
                    <p>Hi {user_name},</p>
                    <p>We've successfully synced <strong>{notebook_count}</strong> notebook(s) from your reMarkable tablet.</p>
                    <p>Your notebooks are now available in the rMirror Cloud dashboard.</p>
                    <p>
                        <a href="https://rmirror.io"
                           style="display: inline-block; padding: 10px 20px; background-color: #6B46C1; color: white; text-decoration: none; border-radius: 5px;">
                            View Your Notebooks
                        </a>
                    </p>
                </div>
            </body>
        </html>
        """

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
        color_map = {
            "info": "#3B82F6",
            "warning": "#F59E0B",
            "error": "#EF4444",
            "critical": "#991B1B"
        }

        color = color_map.get(severity, "#3B82F6")

        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <div style="background-color: {color}; color: white; padding: 15px; border-radius: 5px;">
                        <h2 style="margin: 0;">{severity.upper()}: {subject}</h2>
                    </div>
                    <div style="margin-top: 20px; padding: 15px; background-color: #f9fafb; border-left: 4px solid {color};">
                        <pre style="white-space: pre-wrap; font-family: monospace;">{message}</pre>
                    </div>
                    <p style="margin-top: 20px; color: #6B7280; font-size: 12px;">
                        This is an automated alert from rMirror Cloud monitoring system.
                    </p>
                </div>
            </body>
        </html>
        """

        return self.send_email(
            to_email=settings.admin_email,
            subject=f"[{severity.upper()}] rMirror Cloud - {subject}",
            html_content=html_content
        )


# Singleton instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get or create EmailService singleton"""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
