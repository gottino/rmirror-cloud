"""Email drip campaign service for onboarding."""

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.notebook import Notebook
from app.models.page import Page
from app.models.user import User
from app.utils.email import get_email_service

logger = logging.getLogger(__name__)


class DripEmailService:
    """Checks and sends time-based drip emails for onboarding."""

    def has_sent(self, user: User, email_id: str) -> bool:
        """Check if a specific drip email has been sent."""
        sent = (user.drip_emails_sent or "").split(",")
        return email_id in sent

    def mark_sent(self, db: Session, user: User, email_id: str):
        """Mark a drip email as sent."""
        sent = [s for s in (user.drip_emails_sent or "").split(",") if s]
        if email_id not in sent:
            sent.append(email_id)
            user.drip_emails_sent = ",".join(sent)
            db.commit()

    async def process_user_drips(self, db: Session, user: User):
        """Check and send any pending drip emails for a user."""
        email_service = get_email_service()
        now = datetime.utcnow()

        # E3: Agent nudge - 24h after signup, no agent connected
        if (not self.has_sent(user, "E3")
            and not user.agent_first_connected_at
            and user.created_at < now - timedelta(hours=24)):

            success = email_service.send_agent_nudge_email(
                user_email=user.email,
                user_name=user.full_name or user.email.split("@")[0],
            )
            if success:
                self.mark_sent(db, user, "E3")
                logger.info(f"Sent E3 (agent nudge) to {user.email}")

        # E4: First sync celebration - triggered by first_notebook_synced_at
        if (not self.has_sent(user, "E4")
            and user.first_notebook_synced_at):

            # Get notebook/page counts for the email
            notebook_count = db.query(Notebook).filter(Notebook.user_id == user.id).count()
            page_count = db.query(Page).join(Notebook).filter(Notebook.user_id == user.id).count()

            success = email_service.send_first_sync_celebration_email(
                user_email=user.email,
                user_name=user.full_name or user.email.split("@")[0],
                notebook_count=notebook_count,
                page_count=page_count,
            )
            if success:
                self.mark_sent(db, user, "E4")
                logger.info(f"Sent E4 (first sync celebration) to {user.email}")

        # E5: First OCR celebration - triggered by first_ocr_completed_at
        if (not self.has_sent(user, "E5")
            and user.first_ocr_completed_at):

            # Try to get a snippet of OCR'd text
            ocr_page = (
                db.query(Page)
                .join(Notebook)
                .filter(Notebook.user_id == user.id, Page.ocr_status == "completed", Page.ocr_text.isnot(None))
                .first()
            )
            snippet = ocr_page.ocr_text[:200] if ocr_page and ocr_page.ocr_text else None

            success = email_service.send_first_ocr_celebration_email(
                user_email=user.email,
                user_name=user.full_name or user.email.split("@")[0],
                ocr_snippet=snippet,
            )
            if success:
                self.mark_sent(db, user, "E5")
                logger.info(f"Sent E5 (first OCR celebration) to {user.email}")

        # E6: Notion nudge - 48h after signup, no Notion connected
        if (not self.has_sent(user, "E6")
            and not user.notion_connected_at
            and user.created_at < now - timedelta(hours=48)):

            success = email_service.send_notion_nudge_email(
                user_email=user.email,
                user_name=user.full_name or user.email.split("@")[0],
            )
            if success:
                self.mark_sent(db, user, "E6")
                logger.info(f"Sent E6 (Notion nudge) to {user.email}")

        # E7: Feedback request - 7 days after signup
        if (not self.has_sent(user, "E7")
            and user.created_at < now - timedelta(days=7)):

            success = email_service.send_feedback_request_email(
                user_email=user.email,
                user_name=user.full_name or user.email.split("@")[0],
            )
            if success:
                self.mark_sent(db, user, "E7")
                logger.info(f"Sent E7 (feedback request) to {user.email}")

    async def process_all_drips(self):
        """Process drip emails for all eligible users."""
        db = SessionLocal()
        try:
            # Get active users who signed up in the last 30 days and haven't completed onboarding
            cutoff = datetime.utcnow() - timedelta(days=30)
            users = (
                db.query(User)
                .filter(
                    User.is_active == True,
                    User.created_at > cutoff,
                )
                .all()
            )

            for user in users:
                try:
                    await self.process_user_drips(db, user)
                except Exception as e:
                    logger.error(f"Error processing drips for user {user.email}: {e}")
        finally:
            db.close()


# Singleton
_drip_service = None


def get_drip_email_service() -> DripEmailService:
    global _drip_service
    if _drip_service is None:
        _drip_service = DripEmailService()
    return _drip_service
