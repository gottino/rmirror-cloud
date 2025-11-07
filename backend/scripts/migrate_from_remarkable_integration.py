#!/usr/bin/env python3
"""
Migrate data from remarkable-integration database to rmirror-cloud.

This script:
1. Reads notebooks and OCR text from remarkable-integration DB
2. Migrates to rmirror-cloud database
3. Preserves UUIDs for deduplication
4. Links all data to a specified user
"""

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.notebook import Notebook, DocumentType
from app.models.page import Page, OcrStatus


class MigrationStats:
    """Track migration statistics."""

    def __init__(self):
        self.notebooks_migrated = 0
        self.notebooks_skipped = 0
        self.pages_migrated = 0
        self.pages_skipped = 0
        self.errors = []

    def print_summary(self):
        """Print migration summary."""
        print("\n" + "="*60)
        print("MIGRATION SUMMARY")
        print("="*60)
        print(f"Notebooks migrated: {self.notebooks_migrated}")
        print(f"Notebooks skipped:  {self.notebooks_skipped}")
        print(f"Pages migrated:     {self.pages_migrated}")
        print(f"Pages skipped:      {self.pages_skipped}")

        if self.errors:
            print(f"\nErrors encountered: {len(self.errors)}")
            for error in self.errors[:10]:  # Show first 10 errors
                print(f"  - {error}")
            if len(self.errors) > 10:
                print(f"  ... and {len(self.errors) - 10} more")
        else:
            print("\n✅ Migration completed successfully with no errors!")
        print("="*60)


def find_remarkable_integration_db():
    """Find the remarkable-integration database."""
    possible_paths = [
        Path.home() / "Documents" / "Development" / "remarkable-integration" / "data" / "remarkable_pipeline.db",
        Path.home() / ".remarkable-integration" / "remarkable_pipeline.db",
        Path.home() / "Documents" / "Development" / "remarkable-integration" / "remarkable_integration.db",
        Path.home() / "Documents" / "Development" / "remarkable-integration" / "data" / "remarkable_integration.db",
    ]

    for path in possible_paths:
        if path.exists():
            return path

    return None


def migrate_notebooks(old_conn, new_session: Session, user_id: int, stats: MigrationStats):
    """
    Migrate notebooks from old database to new.

    Args:
        old_conn: Connection to remarkable-integration database
        new_session: SQLAlchemy session for rmirror-cloud
        user_id: User ID to assign notebooks to
        stats: Migration statistics tracker
    """
    print("\n📚 Migrating notebooks...")

    cursor = old_conn.cursor()
    cursor.execute("""
        SELECT
            notebook_uuid,
            visible_name,
            document_type,
            last_modified,
            authors,
            publisher,
            publication_date,
            pinned,
            item_type,
            parent_uuid,
            full_path
        FROM notebook_metadata
        WHERE deleted = FALSE OR deleted IS NULL
        ORDER BY visible_name
    """)

    for row in cursor.fetchall():
        notebook_uuid = row[0]
        visible_name = row[1] or f"Untitled {notebook_uuid[:8]}"
        document_type = row[2] or "unknown"
        last_modified = row[3]
        authors = row[4]
        publisher = row[5]
        publication_date = row[6]
        pinned = row[7]
        item_type = row[8]
        parent_uuid = row[9]
        full_path = row[10]

        # Check if notebook already exists
        existing = new_session.query(Notebook).filter(
            Notebook.user_id == user_id,
            Notebook.notebook_uuid == notebook_uuid
        ).first()

        if existing:
            print(f"  ⏭️  Skipping existing: {visible_name} ({notebook_uuid[:8]})")
            stats.notebooks_skipped += 1
            continue

        # Map document type to enum
        # CollectionType means it's a folder in reMarkable
        if item_type == "CollectionType":
            doc_type = DocumentType.FOLDER
        elif document_type == "epub":
            doc_type = DocumentType.EPUB
        elif document_type == "pdf":
            doc_type = DocumentType.PDF
        else:
            doc_type = DocumentType.NOTEBOOK

        # Create metadata dict
        metadata = {
            "item_type": item_type,
            "parent_uuid": parent_uuid,
            "pinned": bool(pinned),
            "authors": authors,
            "publisher": publisher,
            "publication_date": publication_date,
        }

        # Parse last_modified date safely
        last_synced = datetime.utcnow()
        if last_modified:
            try:
                last_synced = datetime.fromisoformat(last_modified)
            except (ValueError, TypeError):
                # Invalid date format, use current time
                pass

        # Create notebook
        try:
            notebook = Notebook(
                user_id=user_id,
                notebook_uuid=notebook_uuid,
                visible_name=visible_name,
                document_type=doc_type,
                parent_uuid=parent_uuid,
                full_path=full_path,
                author=authors,
                metadata_json=json.dumps(metadata),
                last_synced_at=last_synced
            )

            new_session.add(notebook)
            new_session.flush()  # Get the ID

            print(f"  ✅ Migrated: {visible_name} ({notebook_uuid[:8]}) -> ID {notebook.id}")
            stats.notebooks_migrated += 1

        except Exception as e:
            error_msg = f"Failed to migrate notebook {notebook_uuid}: {e}"
            print(f"  ❌ {error_msg}")
            stats.errors.append(error_msg)
            new_session.rollback()
            continue

    new_session.commit()
    print(f"\n✅ Notebooks migration complete: {stats.notebooks_migrated} migrated, {stats.notebooks_skipped} skipped")


def migrate_pages(old_conn, new_session: Session, user_id: int, stats: MigrationStats):
    """
    Migrate page OCR text from old database to new.

    Args:
        old_conn: Connection to remarkable-integration database
        new_session: SQLAlchemy session for rmirror-cloud
        user_id: User ID to assign pages to
        stats: Migration statistics tracker
    """
    print("\n📄 Migrating pages with OCR text...")

    cursor = old_conn.cursor()
    cursor.execute("""
        SELECT
            notebook_uuid,
            page_uuid,
            page_number,
            text,
            confidence
        FROM notebook_text_extractions
        ORDER BY notebook_uuid, page_number
    """)

    current_notebook_uuid = None
    current_notebook = None

    for row in cursor.fetchall():
        notebook_uuid = row[0]
        page_uuid = row[1]
        page_number = row[2]
        ocr_text = row[3]
        confidence = row[4]

        # Get notebook (cache to avoid repeated queries)
        if notebook_uuid != current_notebook_uuid:
            current_notebook = new_session.query(Notebook).filter(
                Notebook.user_id == user_id,
                Notebook.notebook_uuid == notebook_uuid
            ).first()
            current_notebook_uuid = notebook_uuid

            if not current_notebook:
                if stats.pages_migrated == 0:  # Only log first error
                    error_msg = f"Notebook {notebook_uuid} not found for page {page_uuid} (will skip pages for missing notebooks)"
                    stats.errors.append(error_msg)
                stats.pages_skipped += 1
                continue

        # Check if page already exists
        existing_page = new_session.query(Page).filter(
            Page.notebook_id == current_notebook.id,
            Page.page_uuid == page_uuid
        ).first()

        if existing_page:
            stats.pages_skipped += 1
            continue

        # Create page with OCR text
        try:
            page = Page(
                notebook_id=current_notebook.id,
                page_number=page_number,
                page_uuid=page_uuid,
                ocr_text=ocr_text,
                ocr_status=OcrStatus.COMPLETED,
                ocr_completed_at=datetime.utcnow()
            )

            new_session.add(page)

            if stats.pages_migrated % 100 == 0:
                new_session.flush()  # Periodic flush for progress
                print(f"  📊 Progress: {stats.pages_migrated} pages migrated...")

            stats.pages_migrated += 1

        except Exception as e:
            error_msg = f"Failed to migrate page {page_uuid} from notebook {notebook_uuid}: {e}"
            stats.errors.append(error_msg)
            continue

    new_session.commit()
    print(f"\n✅ Pages migration complete: {stats.pages_migrated} migrated, {stats.pages_skipped} skipped")


def main():
    """Run the migration."""
    print("="*60)
    print("reMarkable Integration → rmirror-cloud Migration")
    print("="*60)

    # Find source database
    print("\n🔍 Locating databases...")
    old_db_path = find_remarkable_integration_db()

    if not old_db_path:
        print("\n❌ Could not find remarkable-integration database!")
        print("\nPlease provide the path to your remarkable-integration database:")
        old_db_path = input("Path: ").strip()
        old_db_path = Path(old_db_path)

        if not old_db_path.exists():
            print(f"❌ Database not found at: {old_db_path}")
            return 1

    print(f"  ✅ Source DB: {old_db_path}")

    # Find target database
    new_db_path = Path(__file__).parent.parent / "rmirror.db"

    if not new_db_path.exists():
        print(f"\n❌ rmirror-cloud database not found at: {new_db_path}")
        return 1

    print(f"  ✅ Target DB: {new_db_path}")

    # Get user ID
    print("\n👤 Enter your user ID (from rmirror-cloud):")
    print("   (Check with: sqlite3 rmirror.db 'SELECT id, email FROM users')")
    user_id_input = input("User ID: ").strip()

    try:
        user_id = int(user_id_input)
    except ValueError:
        print("❌ Invalid user ID. Must be a number.")
        return 1

    # Confirm before proceeding
    print("\n⚠️  Ready to migrate:")
    print(f"   Source: {old_db_path}")
    print(f"   Target: {new_db_path}")
    print(f"   User ID: {user_id}")
    print("\nThis will copy all notebooks and OCR text to rmirror-cloud.")
    confirm = input("\nProceed? (yes/no): ").strip().lower()

    if confirm not in ['yes', 'y']:
        print("❌ Migration cancelled.")
        return 0

    # Initialize statistics
    stats = MigrationStats()

    # Connect to databases
    print("\n🔄 Starting migration...")
    old_conn = sqlite3.connect(str(old_db_path))
    old_conn.row_factory = sqlite3.Row

    engine = create_engine(f"sqlite:///{new_db_path}")
    new_session = Session(engine)

    try:
        # Migrate notebooks first
        migrate_notebooks(old_conn, new_session, user_id, stats)

        # Then migrate pages
        migrate_pages(old_conn, new_session, user_id, stats)

        # Print summary
        stats.print_summary()

        return 0

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        new_session.rollback()
        return 1

    finally:
        old_conn.close()
        new_session.close()


if __name__ == "__main__":
    sys.exit(main())
