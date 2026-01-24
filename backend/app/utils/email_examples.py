"""
Example usage of email service in rMirror Cloud backend
This file shows how to integrate email notifications into your workflows
"""

from typing import List

from app.models.notebook import Notebook
from app.models.user import User
from app.utils.email import get_email_service


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
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', system-ui, sans-serif; line-height: 1.6; color: #2d2a2e; background-color: #faf8f5;">
            <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                <!-- Header -->
                <div style="text-align: center; margin-bottom: 32px;">
                    <div style="display: inline-block; padding: 12px 24px; background-color: #d4a574; border-radius: 8px; margin-bottom: 16px;">
                        <p style="color: #ffffff; font-size: 14px; font-weight: 600; margin: 0; text-transform: uppercase; letter-spacing: 0.5px;">⚠️ Processing Issue</p>
                    </div>
                    <h1 style="color: #2d2a2e; font-size: 28px; font-weight: 600; margin: 0;">OCR Processing Issue</h1>
                </div>

                <!-- Content card -->
                <div style="background-color: #ffffff; border-radius: 12px; padding: 32px; box-shadow: 0 4px 12px rgba(45, 42, 46, 0.08); margin-bottom: 24px;">
                    <p style="color: #2d2a2e; font-size: 16px; margin: 0 0 20px 0;">Hi {user.name or 'there'},</p>
                    <p style="color: #2d2a2e; font-size: 16px; margin: 0 0 24px 0;">We encountered an issue processing one of your notebooks.</p>

                    <!-- Info box -->
                    <div style="background-color: #faf8f5; padding: 16px; border-radius: 8px; border-left: 3px solid #d4a574; margin-bottom: 24px;">
                        <p style="color: #8b8680; font-size: 13px; margin: 0 0 4px 0; font-weight: 600;">Notebook ID:</p>
                        <p style="color: #2d2a2e; font-size: 14px; font-family: 'SF Mono', monospace; margin: 0;">{notebook_id}</p>
                    </div>

                    <p style="color: #2d2a2e; font-size: 15px; margin: 0;">We're looking into this and will retry automatically. If the issue persists, please contact our support team.</p>
                </div>

                <!-- Footer -->
                <div style="text-align: center; padding-top: 24px; border-top: 1px solid #e8e4df;">
                    <p style="color: #8b8680; font-size: 13px; margin: 0;">
                        Questions? We're here to help.
                    </p>
                </div>
            </div>
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
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', system-ui, sans-serif; line-height: 1.6; color: #2d2a2e; background-color: #faf8f5;">
            <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                <!-- Header -->
                <div style="text-align: center; margin-bottom: 40px; padding-bottom: 24px; border-bottom: 1px solid #e8e4df;">
                    <h1 style="color: #2d2a2e; font-size: 32px; font-weight: 600; margin: 0 0 8px 0;">Your Weekly rMirror Summary</h1>
                    <p style="color: #8b8680; font-size: 16px; margin: 0;">Here's what happened this week</p>
                </div>

                <!-- Content card -->
                <div style="background-color: #ffffff; border-radius: 12px; padding: 32px; box-shadow: 0 4px 12px rgba(45, 42, 46, 0.08); margin-bottom: 24px;">
                    <p style="color: #2d2a2e; font-size: 16px; margin: 0 0 24px 0;">Hi {user.name or 'there'},</p>

                    <!-- Stats grid -->
                    <div style="background-color: #faf8f5; padding: 24px; border-radius: 8px; margin-bottom: 28px;">
                        <h3 style="margin: 0 0 20px 0; color: #2d2a2e; font-size: 18px; font-weight: 600;">Activity This Week</h3>

                        <div style="margin-bottom: 16px; padding-bottom: 16px; border-bottom: 1px solid #e8e4df;">
                            <div style="display: flex; align-items: center; justify-content: space-between;">
                                <span style="color: #8b8680; font-size: 15px;">📝 Notebooks synced</span>
                                <span style="color: #2d2a2e; font-size: 24px; font-weight: 700;">{stats['notebooks_synced']}</span>
                            </div>
                        </div>

                        <div style="margin-bottom: 16px; padding-bottom: 16px; border-bottom: 1px solid #e8e4df;">
                            <div style="display: flex; align-items: center; justify-content: space-between;">
                                <span style="color: #8b8680; font-size: 15px;">📄 Pages processed</span>
                                <span style="color: #2d2a2e; font-size: 24px; font-weight: 700;">{stats['pages_processed']}</span>
                            </div>
                        </div>

                        <div>
                            <div style="display: flex; align-items: center; justify-content: space-between;">
                                <span style="color: #8b8680; font-size: 15px;">🔍 Notebooks transcribed</span>
                                <span style="color: #c85a54; font-size: 24px; font-weight: 700;">{stats['ocr_completed']}</span>
                            </div>
                        </div>
                    </div>

                    <p style="color: #2d2a2e; font-size: 15px; margin: 0 0 24px 0; text-align: center; color: #7a9c89; font-weight: 500;">Keep up the great work!</p>

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
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Segoe UI', system-ui, sans-serif; line-height: 1.6; color: #2d2a2e; background-color: #faf8f5;">
            <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
                <!-- Header -->
                <div style="text-align: center; margin-bottom: 32px;">
                    <div style="display: inline-block; padding: 12px 24px; background-color: #d4a574; border-radius: 8px; margin-bottom: 16px;">
                        <p style="color: #ffffff; font-size: 14px; font-weight: 600; margin: 0; text-transform: uppercase; letter-spacing: 0.5px;">⏰ Action Required</p>
                    </div>
                    <h1 style="color: #2d2a2e; font-size: 28px; font-weight: 600; margin: 0;">Subscription Expiring Soon</h1>
                </div>

                <!-- Content card -->
                <div style="background-color: #ffffff; border-radius: 12px; padding: 32px; box-shadow: 0 4px 12px rgba(45, 42, 46, 0.08); margin-bottom: 24px;">
                    <p style="color: #2d2a2e; font-size: 16px; margin: 0 0 20px 0;">Hi {user.name or 'there'},</p>
                    <p style="color: #2d2a2e; font-size: 16px; margin: 0 0 24px 0;">Your rMirror Cloud subscription will expire in <strong style="color: #d4a574; font-size: 18px;">{days_remaining} days</strong>.</p>

                    <!-- Features box -->
                    <div style="background-color: #faf8f5; padding: 20px; border-radius: 8px; margin-bottom: 28px;">
                        <p style="color: #2d2a2e; font-size: 15px; margin: 0 0 12px 0; font-weight: 600;">Renew now to continue enjoying:</p>
                        <ul style="color: #2d2a2e; font-size: 15px; margin: 0; padding-left: 20px; line-height: 1.8;">
                            <li>Unlimited notebook syncing</li>
                            <li>OCR transcription</li>
                            <li>Cloud storage</li>
                            <li>Integration with Notion & Readwise</li>
                        </ul>
                    </div>

                    <!-- CTA Button -->
                    <div style="text-align: center; margin: 32px 0 0 0;">
                        <a href="https://rmirror.io/billing"
                           style="display: inline-block; padding: 14px 32px; background-color: #c85a54; color: #ffffff; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px; box-shadow: 0 4px 12px rgba(200, 90, 84, 0.25);">
                            Renew Subscription
                        </a>
                    </div>
                </div>

                <!-- Footer -->
                <div style="text-align: center; padding-top: 24px; border-top: 1px solid #e8e4df;">
                    <p style="color: #8b8680; font-size: 13px; margin: 0;">
                        Questions about your subscription? We're here to help.
                    </p>
                </div>
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
