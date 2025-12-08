"""
Example usage of email service in rMirror Cloud backend
This file shows how to integrate email notifications into your workflows
"""

from app.utils.email import get_email_service
from app.models.user import User
from app.models.notebook import Notebook
from typing import List


# Example 1: User Registration Hook
async def on_user_registered(user: User):
    """Called when a new user registers via Clerk webhook"""
    email_service = get_email_service()

    # Send welcome email
    email_service.send_welcome_email(
        user_email=user.email,
        user_name=user.name or "there"
    )

    # Notify admin of new user
    email_service.send_admin_alert(
        subject="New User Registration",
        message=f"New user registered: {user.email} (ID: {user.id})",
        severity="info"
    )


# Example 2: Notebook Sync Completion
async def on_notebooks_synced(user: User, notebooks: List[Notebook]):
    """Called when agent successfully syncs notebooks"""
    email_service = get_email_service()

    # Only notify if it's a significant sync (5+ notebooks)
    if len(notebooks) >= 5:
        email_service.send_sync_notification(
            user_email=user.email,
            user_name=user.name or "there",
            notebook_count=len(notebooks)
        )


# Example 3: Error Monitoring
async def on_critical_error(error_type: str, error_message: str, stack_trace: str):
    """Called when a critical error occurs"""
    email_service = get_email_service()

    message = f"""
Error Type: {error_type}
Message: {error_message}

Stack Trace:
{stack_trace}
    """

    email_service.send_admin_alert(
        subject=f"Critical Error: {error_type}",
        message=message,
        severity="critical"
    )


# Example 4: OCR Processing Failed
async def on_ocr_failed(user: User, notebook_id: str, error: str):
    """Called when OCR processing fails for a notebook"""
    email_service = get_email_service()

    # Notify user
    html_content = f"""
    <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>OCR Processing Issue</h2>
            <p>Hi {user.name or 'there'},</p>
            <p>We encountered an issue processing one of your notebooks.</p>
            <p><strong>Notebook ID:</strong> {notebook_id}</p>
            <p>We're looking into this and will retry automatically. If the issue persists, please contact support.</p>
        </body>
    </html>
    """

    email_service.send_email(
        to_email=user.email,
        subject="Notebook Processing Issue",
        html_content=html_content,
        to_name=user.name
    )

    # Notify admin
    email_service.send_admin_alert(
        subject="OCR Processing Failed",
        message=f"User: {user.email}\nNotebook: {notebook_id}\nError: {error}",
        severity="warning"
    )


# Example 5: Weekly Summary Email
async def send_weekly_summary(user: User, stats: dict):
    """Send weekly activity summary to user"""
    email_service = get_email_service()

    html_content = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h1 style="color: #6B46C1;">Your Weekly rMirror Summary</h1>
                <p>Hi {user.name or 'there'},</p>
                <p>Here's what happened this week:</p>

                <div style="background-color: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #6B46C1;">Activity This Week</h3>
                    <ul style="list-style: none; padding: 0;">
                        <li>📝 <strong>{stats['notebooks_synced']}</strong> notebooks synced</li>
                        <li>📄 <strong>{stats['pages_processed']}</strong> pages processed</li>
                        <li>🔍 <strong>{stats['ocr_completed']}</strong> notebooks transcribed</li>
                    </ul>
                </div>

                <p>Keep up the great work!</p>

                <p style="margin-top: 30px;">
                    <a href="https://rmirror.io"
                       style="display: inline-block; padding: 10px 20px; background-color: #6B46C1; color: white; text-decoration: none; border-radius: 5px;">
                        View Your Notebooks
                    </a>
                </p>
            </div>
        </body>
    </html>
    """

    email_service.send_email(
        to_email=user.email,
        subject="Your Weekly rMirror Summary",
        html_content=html_content,
        to_name=user.name
    )


# Example 6: Subscription/Payment Notifications
async def on_subscription_expiring(user: User, days_remaining: int):
    """Notify user when subscription is about to expire"""
    email_service = get_email_service()

    html_content = f"""
    <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h1 style="color: #F59E0B;">Subscription Expiring Soon</h1>
                <p>Hi {user.name or 'there'},</p>
                <p>Your rMirror Cloud subscription will expire in <strong>{days_remaining} days</strong>.</p>
                <p>Renew now to continue enjoying:</p>
                <ul>
                    <li>Unlimited notebook syncing</li>
                    <li>OCR transcription</li>
                    <li>Cloud storage</li>
                </ul>
                <p>
                    <a href="https://rmirror.io/billing"
                       style="display: inline-block; padding: 10px 20px; background-color: #6B46C1; color: white; text-decoration: none; border-radius: 5px;">
                        Renew Subscription
                    </a>
                </p>
            </div>
        </body>
    </html>
    """

    email_service.send_email(
        to_email=user.email,
        subject=f"Subscription Expiring in {days_remaining} Days",
        html_content=html_content,
        to_name=user.name
    )


# Example 7: Server Health Monitoring
async def send_server_health_alert(metric: str, current_value: float, threshold: float):
    """Send alert when server metrics exceed thresholds"""
    email_service = get_email_service()

    severity = "warning" if current_value < threshold * 1.5 else "critical"

    message = f"""
Metric: {metric}
Current Value: {current_value:.2f}
Threshold: {threshold:.2f}
Percentage: {(current_value / threshold * 100):.1f}%

Action Required: Please check server status and take appropriate action.
    """

    email_service.send_admin_alert(
        subject=f"Server Alert: {metric} High",
        message=message,
        severity=severity
    )
