#!/usr/bin/env python3
"""Create pending pages for manual testing of retroactive processing.

Usage:
    poetry run python tests/manual_test_data/create_pending_pages.py <email> <count>

Example:
    poetry run python tests/manual_test_data/create_pending_pages.py test@example.com 20
    poetry run python tests/manual_test_data/create_pending_pages.py test@example.com 100

This script creates PENDING_QUOTA pages with staggered timestamps for testing:
- Retroactive OCR processing
- Pending page display in dashboard
- Hard cap enforcement (100 pending pages)
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


from app.database import get_db
from app.models.notebook import DocumentType, Notebook
from app.models.page import OcrStatus, Page
from app.models.user import User


def create_pending_pages(email: str, count: int = 20) -> None:
    """
    Create pending pages for a user.

    Args:
        email: User email address
        count: Number of pending pages to create (default: 20)
    """
    db = next(get_db())

    try:
        # Get user
        user = db.query(User).filter(User.email == email).first()
        if not user:
            print(f"❌ User not found: {email}")
            print("\nAvailable test users:")
            test_users = db.query(User).filter(User.email.like('%test%')).all()
            for u in test_users[:10]:
                print(f"  - {u.email}")
            return

        print(f"📧 Found user: {user.email} (ID: {user.id})")

        # Get or create test notebook
        notebook_uuid = f"pending-pages-test-{user.id}"
        notebook = db.query(Notebook).filter(
            Notebook.user_id == user.id,
            Notebook.notebook_uuid == notebook_uuid
        ).first()

        if not notebook:
            notebook = Notebook(
                user_id=user.id,
                notebook_uuid=notebook_uuid,
                visible_name=f"Pending Pages Test ({count} pages)",
                document_type=DocumentType.NOTEBOOK,
                created_at=datetime.utcnow(),
            )
            db.add(notebook)
            db.commit()
            db.refresh(notebook)
            print(f"📓 Created test notebook: {notebook.visible_name} (ID: {notebook.id})")
        else:
            print(f"📓 Using existing notebook: {notebook.visible_name} (ID: {notebook.id})")

        # Create pending pages with staggered timestamps
        print(f"\n📄 Creating {count} pending pages...")
        pages_created = 0

        for i in range(count):
            # Create pages with timestamps from oldest to newest
            # (newest will be processed first during retroactive processing)
            created_at = datetime.utcnow() - timedelta(days=count - i)

            # Check if page already exists
            page_uuid = f"pending-page-{notebook_uuid}-{i}"
            existing_page = db.query(Page).filter(
                Page.notebook_id == notebook.id,
                Page.page_uuid == page_uuid
            ).first()

            if existing_page:
                # Update existing page to PENDING_QUOTA
                existing_page.ocr_status = OcrStatus.PENDING_QUOTA
                existing_page.ocr_text = None
                existing_page.ocr_completed_at = None
                existing_page.created_at = created_at
                existing_page.updated_at = datetime.utcnow()
                print(f"  ♻️  Updated page {i+1}/{count} (ID: {existing_page.id})")
            else:
                # Create new page
                page = Page(
                    notebook_id=notebook.id,
                    page_uuid=page_uuid,
                    s3_key=f"s3://test-bucket/{page_uuid}.rm",
                    pdf_s3_key=f"s3://test-bucket/{page_uuid}.pdf",  # Required for processing
                    file_hash=f"test-hash-{i}",
                    ocr_status=OcrStatus.PENDING_QUOTA,
                    ocr_text=None,
                    ocr_completed_at=None,
                    created_at=created_at,
                    updated_at=datetime.utcnow(),
                )
                db.add(page)
                pages_created += 1
                print(f"  ✅ Created page {i+1}/{count} (created_at: {created_at.date()})")

            # Commit every 10 pages to avoid huge transaction
            if (i + 1) % 10 == 0:
                db.commit()
                print(f"  💾 Committed batch ({i+1}/{count})")

        # Final commit
        db.commit()

        # Verify creation
        pending_count = db.query(Page).filter(
            Page.notebook_id == notebook.id,
            Page.ocr_status == OcrStatus.PENDING_QUOTA
        ).count()

        print("\n✅ Success!")
        print(f"   Total pending pages: {pending_count}")
        print(f"   New pages created: {pages_created}")
        print(f"   Notebook ID: {notebook.id}")
        print("\n🔍 View pages:")
        print("   SELECT page_uuid, ocr_status, created_at")
        print("   FROM pages")
        print(f"   WHERE notebook_id = {notebook.id}")
        print("   ORDER BY created_at ASC;")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


def show_usage():
    """Show usage instructions."""
    print("Usage: poetry run python tests/manual_test_data/create_pending_pages.py <email> <count>")
    print()
    print("Examples:")
    print("  # Create 20 pending pages")
    print("  poetry run python tests/manual_test_data/create_pending_pages.py test@example.com 20")
    print()
    print("  # Create 100 pending pages (for hard cap testing)")
    print("  poetry run python tests/manual_test_data/create_pending_pages.py test@example.com 100")
    print()
    print("  # Create 50 pending pages (for retroactive processing testing)")
    print("  poetry run python tests/manual_test_data/create_pending_pages.py test@example.com 50")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        show_usage()
        sys.exit(1)

    email = sys.argv[1]
    try:
        count = int(sys.argv[2])
        if count < 1 or count > 200:
            print("❌ Count must be between 1 and 200")
            sys.exit(1)
    except ValueError:
        print("❌ Count must be a number")
        show_usage()
        sys.exit(1)

    create_pending_pages(email, count)
