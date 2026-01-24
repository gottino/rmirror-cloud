#!/usr/bin/env python3
"""Reset user quota and trigger retroactive OCR processing.

Usage:
    poetry run python tests/manual_test_data/reset_quota_and_process.py <email>

Example:
    poetry run python tests/manual_test_data/reset_quota_and_process.py test@example.com

This script:
1. Resets user's quota to 0/30 (new period)
2. Triggers retroactive OCR processing for PENDING_QUOTA pages
3. Processes newest pages first (up to quota limit)
4. Reports results

Use this to test:
- Quota reset behavior
- Retroactive processing job
- Processing order (newest first)
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


from app.database import get_db
from app.jobs.process_pending_pages import process_pending_pages_for_user
from app.models.page import OcrStatus, Page
from app.models.user import User
from app.services import quota_service


async def reset_quota_and_process(email: str, trigger_processing: bool = True) -> None:
    """
    Reset quota and optionally trigger retroactive processing.

    Args:
        email: User email address
        trigger_processing: If True, run retroactive processing job
    """
    db = next(get_db())

    try:
        # Get user
        user = db.query(User).filter(User.email == email).first()
        if not user:
            print(f"❌ User not found: {email}")
            return

        print(f"📧 Found user: {user.email} (ID: {user.id})")

        # Get current quota status
        quota = quota_service.get_or_create_quota(db, user.id)
        print("\n📊 Current quota status:")
        print(f"   Used: {quota.used}/{quota.limit} ({quota.percentage_used:.1f}%)")
        print(f"   Period: {quota.period_start.date()} to {quota.reset_at.date()}")

        # Count pending pages
        pending_count = (
            db.query(Page)
            .join(Page.notebook)
            .filter(
                Page.notebook.has(user_id=user.id),
                Page.ocr_status == OcrStatus.PENDING_QUOTA,
            )
            .count()
        )
        print(f"   Pending pages: {pending_count}")

        if pending_count == 0:
            print("\n⚠️  No pending pages to process.")
            print("   Use create_pending_pages.py to create test pages first.")

        # Reset quota
        print("\n🔄 Resetting quota...")
        quota = quota_service.reset_quota(
            db, user.id, trigger_retroactive_processing=False  # We'll do it manually
        )
        print(f"   ✅ Quota reset to {quota.used}/{quota.limit}")
        print(f"   New period: {quota.period_start.date()} to {quota.reset_at.date()}")

        if not trigger_processing:
            print("\n⏭️  Skipping retroactive processing (manual mode)")
            return

        if pending_count == 0:
            print("\n⏭️  Skipping retroactive processing (no pending pages)")
            return

        # Trigger retroactive processing
        print("\n🔄 Starting retroactive OCR processing...")
        print(f"   Processing up to {quota.limit} pages (newest first)")

        # Mock OCR service for testing (if needed)
        # In real usage, this will call actual OCR API
        from unittest.mock import AsyncMock, patch

        with patch(
            "app.core.ocr_service.OCRService.extract_text_from_pdf"
        ) as mock_ocr, patch(
            "app.dependencies.get_storage_service"
        ) as mock_storage_service:

            # Mock OCR to return test text
            async def mock_extract_text(pdf_bytes):
                return f"Test OCR text extracted at {datetime.utcnow().isoformat()}"

            mock_ocr.side_effect = mock_extract_text

            # Mock storage download
            mock_storage = AsyncMock()
            mock_storage.download_file = AsyncMock(return_value=b"fake_pdf_bytes")
            mock_storage_service.return_value = mock_storage

            # Run processing
            processed_count = await process_pending_pages_for_user(db, user.id)

        # Get final status
        db.refresh(quota)
        final_pending = (
            db.query(Page)
            .join(Page.notebook)
            .filter(
                Page.notebook.has(user_id=user.id),
                Page.ocr_status == OcrStatus.PENDING_QUOTA,
            )
            .count()
        )

        final_completed = (
            db.query(Page)
            .join(Page.notebook)
            .filter(
                Page.notebook.has(user_id=user.id),
                Page.ocr_status == OcrStatus.COMPLETED,
            )
            .count()
        )

        # Report results
        print("\n✅ Retroactive processing complete!")
        print(f"   Pages processed: {processed_count}")
        print(f"   Quota used: {quota.used}/{quota.limit}")
        print(f"   Still pending: {final_pending}")
        print(f"   Total completed: {final_completed}")

        if final_pending > 0:
            print(f"\n📝 Note: {final_pending} pages still pending")
            print(f"   (Quota exhausted after processing {processed_count} pages)")

        # Show newest processed pages
        print("\n🔍 Newest processed pages:")
        recent_processed = (
            db.query(Page)
            .join(Page.notebook)
            .filter(
                Page.notebook.has(user_id=user.id),
                Page.ocr_status == OcrStatus.COMPLETED,
                Page.ocr_completed_at.isnot(None),
            )
            .order_by(Page.created_at.desc())
            .limit(5)
            .all()
        )

        for i, page in enumerate(recent_processed, 1):
            print(
                f"   {i}. Page {page.page_uuid[:20]}... "
                f"(created: {page.created_at.date()}, "
                f"processed: {page.ocr_completed_at.strftime('%H:%M:%S')})"
            )

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


def show_usage():
    """Show usage instructions."""
    print("Usage: poetry run python tests/manual_test_data/reset_quota_and_process.py <email>")
    print()
    print("Example:")
    print("  poetry run python tests/manual_test_data/reset_quota_and_process.py test@example.com")
    print()
    print("This will:")
    print("  1. Reset quota to 0/30 (new billing period)")
    print("  2. Process pending PENDING_QUOTA pages (newest first)")
    print("  3. Stop when quota exhausted")
    print()
    print("Note: Uses mocked OCR service for testing.")
    print("      In production, actual OCR API will be called.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        show_usage()
        sys.exit(1)

    email = sys.argv[1]

    # Run async function
    asyncio.run(reset_quota_and_process(email))
