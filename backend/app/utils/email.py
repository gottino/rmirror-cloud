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
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', system-ui, sans-serif; line-height: 1.6; color: #2d2a2e; background-color: #faf8f5;">
                <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                    <!-- Header with subtle border -->
                    <div style="text-align: center; margin-bottom: 40px; padding-bottom: 24px; border-bottom: 1px solid #e8e4df;">
                        <h1 style="color: #2d2a2e; font-size: 32px; font-weight: 600; margin: 0 0 8px 0;">Welcome to rMirror</h1>
                        <p style="color: #8b8680; font-size: 16px; margin: 0;">Your reMarkable Notes, Searchable Everywhere</p>
                    </div>

                    <!-- Content card -->
                    <div style="background-color: #ffffff; border-radius: 12px; padding: 32px; box-shadow: 0 4px 12px rgba(45, 42, 46, 0.08); margin-bottom: 24px;">
                        <p style="color: #2d2a2e; font-size: 16px; margin: 0 0 20px 0;">Hi {user_name},</p>
                        <p style="color: #2d2a2e; font-size: 16px; margin: 0 0 24px 0;">Thank you for joining rMirror Cloud. We're excited to help you sync and transcribe your reMarkable notebooks with powerful OCR.</p>

                        <!-- Feature callout -->
                        <div style="background-color: #faf8f5; padding: 16px; border-radius: 8px; border-left: 3px solid #c85a54; margin-bottom: 28px;">
                            <p style="color: #2d2a2e; font-size: 15px; margin: 0; font-weight: 600;">Free tier includes:</p>
                            <p style="color: #8b8680; font-size: 14px; margin: 8px 0 0 0;">30 pages of OCR transcription per month • No credit card required</p>
                        </div>

                        <h2 style="color: #2d2a2e; font-size: 20px; font-weight: 600; margin: 0 0 16px 0;">Getting Started</h2>
                        <p style="color: #2d2a2e; font-size: 15px; margin: 0 0 12px 0;">To start syncing your reMarkable notebooks:</p>
                        <ol style="color: #2d2a2e; font-size: 15px; margin: 0 0 24px 0; padding-left: 20px;">
                            <li style="margin-bottom: 8px;">Visit your <a href="https://rmirror.io/dashboard" style="color: #c85a54; text-decoration: none; font-weight: 500;">dashboard</a> to download the macOS agent</li>
                            <li style="margin-bottom: 8px;">Install the agent and sign in with your account</li>
                            <li style="margin-bottom: 8px;">Your notebooks will automatically sync to the cloud</li>
                        </ol>

                        <!-- CTA Button -->
                        <div style="text-align: center; margin: 32px 0 0 0;">
                            <a href="https://rmirror.io/dashboard"
                               style="display: inline-block; padding: 14px 32px; background-color: #c85a54; color: #ffffff; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px; box-shadow: 0 4px 12px rgba(200, 90, 84, 0.25);">
                                Go to Dashboard
                            </a>
                        </div>
                    </div>

                    <!-- Footer -->
                    <div style="text-align: center; padding-top: 24px; border-top: 1px solid #e8e4df;">
                        <p style="color: #8b8680; font-size: 14px; margin: 0 0 8px 0;">
                            Questions? We're here to help.
                        </p>
                        <p style="color: #2d2a2e; font-size: 14px; margin: 0; font-weight: 600;">
                            The rMirror Team
                        </p>
                    </div>
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
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', system-ui, sans-serif; line-height: 1.6; color: #2d2a2e; background-color: #faf8f5;">
                <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                    <!-- Header -->
                    <div style="text-align: center; margin-bottom: 32px;">
                        <div style="display: inline-block; padding: 12px 24px; background-color: #7a9c89; border-radius: 8px; margin-bottom: 16px;">
                            <p style="color: #ffffff; font-size: 14px; font-weight: 600; margin: 0; text-transform: uppercase; letter-spacing: 0.5px;">✓ Sync Complete</p>
                        </div>
                        <h1 style="color: #2d2a2e; font-size: 28px; font-weight: 600; margin: 0;">Notebooks Synced Successfully</h1>
                    </div>

                    <!-- Content card -->
                    <div style="background-color: #ffffff; border-radius: 12px; padding: 32px; box-shadow: 0 4px 12px rgba(45, 42, 46, 0.08); margin-bottom: 24px;">
                        <p style="color: #2d2a2e; font-size: 16px; margin: 0 0 20px 0;">Hi {user_name},</p>
                        <p style="color: #2d2a2e; font-size: 16px; margin: 0 0 24px 0;">Great news! We've successfully synced <strong style="color: #c85a54;">{notebook_count}</strong> notebook(s) from your reMarkable tablet.</p>

                        <!-- Stats callout -->
                        <div style="background-color: #faf8f5; padding: 20px; border-radius: 8px; text-align: center; margin-bottom: 28px;">
                            <p style="color: #8b8680; font-size: 13px; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 8px 0;">Notebooks Synced</p>
                            <p style="color: #2d2a2e; font-size: 36px; font-weight: 700; margin: 0; line-height: 1;">{notebook_count}</p>
                        </div>

                        <p style="color: #2d2a2e; font-size: 15px; margin: 0 0 24px 0;">Your notebooks are now available in the rMirror Cloud dashboard. View them, search through OCR'd content, and sync to your favorite tools.</p>

                        <!-- CTA Button -->
                        <div style="text-align: center; margin: 32px 0 0 0;">
                            <a href="https://rmirror.io/dashboard"
                               style="display: inline-block; padding: 14px 32px; background-color: #c85a54; color: #ffffff; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px; box-shadow: 0 4px 12px rgba(200, 90, 84, 0.25);">
                                View Your Notebooks
                            </a>
                        </div>
                    </div>

                    <!-- Footer -->
                    <div style="text-align: center; padding-top: 24px; border-top: 1px solid #e8e4df;">
                        <p style="color: #8b8680; font-size: 13px; margin: 0;">
                            Happy note-taking!
                        </p>
                    </div>
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

        html_content = f"""
        <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
            </head>
            <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', system-ui, sans-serif; line-height: 1.6; color: #2d2a2e; background-color: #faf8f5;">
                <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                    <!-- Alert Header -->
                    <div style="background-color: {color}; color: #ffffff; padding: 20px 24px; border-radius: 12px 12px 0 0; margin-bottom: 0;">
                        <p style="color: #ffffff; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; margin: 0 0 8px 0; opacity: 0.9;">{severity.upper()} ALERT</p>
                        <h2 style="color: #ffffff; font-size: 22px; font-weight: 600; margin: 0;">{emoji} {subject}</h2>
                    </div>

                    <!-- Alert Content -->
                    <div style="background-color: #ffffff; padding: 24px; border-radius: 0 0 12px 12px; box-shadow: 0 4px 12px rgba(45, 42, 46, 0.08); margin-bottom: 24px;">
                        <div style="background-color: #faf8f5; padding: 20px; border-radius: 8px; border-left: 4px solid {color};">
                            <pre style="white-space: pre-wrap; font-family: 'SF Mono', 'Menlo', 'Monaco', 'Courier New', monospace; font-size: 13px; line-height: 1.6; color: #2d2a2e; margin: 0; overflow-x: auto;">{message}</pre>
                        </div>
                    </div>

                    <!-- Footer -->
                    <div style="text-align: center; padding-top: 20px; border-top: 1px solid #e8e4df;">
                        <p style="color: #8b8680; font-size: 12px; margin: 0;">
                            Automated alert from rMirror Cloud monitoring system
                        </p>
                    </div>
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
