#!/usr/bin/env python3
"""
Fix Page Ordering from .content Files

This script reads reMarkable .content files (the source of truth) and updates
the page_number values in the database to reflect the correct order.

The .content file contains a "pages" array listing page UUIDs in the correct order.
Index 0 = page 1, index 1 = page 2, etc.

Usage:
    poetry run python fix_page_order_from_content.py --remarkable-dir "~/Library/Containers/..."
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
load_dotenv(Path(__file__).parent / '.env')

from app.models.notebook import Notebook
from app.models.page import Page

# Get database URL from environment
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("❌ DATABASE_URL not found in environment")
    sys.exit(1)


def parse_content_file(content_path: Path) -> dict:
    """Parse a .content file and return its contents."""
    with open(content_path, 'r') as f:
        return json.load(f)


def build_content_map(remarkable_dir: Path) -> dict:
    """Build a map of page_uuid -> (notebook_uuid, page_number) from all .content files."""
    page_to_notebook = {}

    for content_file in remarkable_dir.glob("*.content"):
        notebook_uuid = content_file.stem

        try:
            content_data = parse_content_file(content_file)
            file_type = content_data.get('fileType', '')

            # Only process notebooks and epubs
            if file_type not in ['notebook', 'epub']:
                continue

            # Try both old format (pages array) and new format (cPages.pages array)
            content_pages = content_data.get('pages', [])

            # If pages is empty, try cPages.pages (newer format)
            if not content_pages and 'cPages' in content_data:
                c_pages = content_data['cPages'].get('pages', [])
                # Extract page IDs from cPages format
                content_pages = [p['id'] for p in c_pages if isinstance(p, dict) and 'id' in p]

            for index, page_uuid in enumerate(content_pages):
                page_number = index + 1
                page_to_notebook[page_uuid] = (notebook_uuid, page_number)
        except Exception as e:
            print(f"  Error processing {content_file.name}: {e}")
            continue

    return page_to_notebook


def fix_notebook_pages(
    db,
    notebook_uuid: str,
    content_data: dict,
    page_to_notebook_map: dict,
    dry_run: bool = False
):
    """Fix page ordering for a single notebook based on its .content file."""

    # Find the notebook in database
    notebook = db.query(Notebook).filter(
        Notebook.notebook_uuid == notebook_uuid
    ).first()

    if not notebook:
        print(f"  ⚠️  Notebook {notebook_uuid} not found in database - skipping")
        return

    # Get the pages array from .content file (source of truth)
    # Try both old format (pages array) and new format (cPages.pages array)
    content_pages = content_data.get('pages', [])

    # If pages is empty, try cPages.pages (newer format)
    if not content_pages and 'cPages' in content_data:
        c_pages = content_data['cPages'].get('pages', [])
        # Extract page IDs from cPages format
        content_pages = [p['id'] for p in c_pages if isinstance(p, dict) and 'id' in p]

    if not content_pages:
        page_count = content_data.get('pageCount', 0)
        print(f"  ⚠️  No pages in .content file for {notebook.visible_name} (pageCount={page_count})")
        # If there are pages in DB but none in .content, they're all orphans - move them
        db_pages = db.query(Page).filter(Page.notebook_id == notebook.id).all()
        if db_pages:
            print(f"  📦 {len(db_pages)} pages don't belong to this notebook (will try to move them)")
            moved = 0
            for page in db_pages:
                if page.page_uuid in page_to_notebook_map:
                    correct_notebook_uuid, correct_page_number = page_to_notebook_map[page.page_uuid]
                    correct_notebook = db.query(Notebook).filter(
                        Notebook.notebook_uuid == correct_notebook_uuid
                    ).first()

                    if correct_notebook and correct_notebook.id != notebook.id:
                        print(f"      → Moving {page.page_uuid[:8]}... to '{correct_notebook.visible_name}' (page {correct_page_number})")
                        if not dry_run:
                            page.notebook_id = correct_notebook.id
                            page.page_number = correct_page_number
                            moved += 1
            if not dry_run and moved > 0:
                db.commit()
                print(f"   ✅ Moved {moved} pages")
        return

    print(f"\n📓 {notebook.visible_name}")
    print(f"   UUID: {notebook_uuid}")
    print(f"   .content has {len(content_pages)} pages")

    # Get current pages from database
    db_pages = db.query(Page).filter(
        Page.notebook_id == notebook.id
    ).all()

    print(f"   Database has {len(db_pages)} pages")

    # Create a mapping of page_uuid -> Page object
    pages_by_uuid = {page.page_uuid: page for page in db_pages if page.page_uuid}

    # Track changes
    updates_count = 0
    missing_pages = []
    moved_pages = 0

    # Update page numbers based on .content file order
    for correct_index, page_uuid in enumerate(content_pages):
        correct_page_number = correct_index + 1  # 1-indexed

        if page_uuid in pages_by_uuid:
            page = pages_by_uuid[page_uuid]

            if page.page_number != correct_page_number:
                print(f"   📝 Page {page_uuid[:8]}... : {page.page_number} → {correct_page_number}")

                if not dry_run:
                    page.page_number = correct_page_number
                    updates_count += 1
        else:
            # Page exists in .content but not in database
            missing_pages.append((correct_page_number, page_uuid))

    # Report missing pages
    if missing_pages:
        print(f"   ⚠️  {len(missing_pages)} pages in .content not found in database:")
        for page_num, page_uuid in missing_pages[:5]:  # Show first 5
            print(f"      - Page {page_num}: {page_uuid}")
        if len(missing_pages) > 5:
            print(f"      ... and {len(missing_pages) - 5} more")

    # Handle orphan pages (in database but not in this notebook's .content)
    orphan_pages = [p for p in db_pages if p.page_uuid not in content_pages]
    if orphan_pages:
        print(f"   📦 {len(orphan_pages)} pages don't belong to this notebook:")

        for page in orphan_pages:
            # Find correct notebook for this page
            if page.page_uuid in page_to_notebook_map:
                correct_notebook_uuid, correct_page_number = page_to_notebook_map[page.page_uuid]

                # Find the correct notebook in database
                correct_notebook = db.query(Notebook).filter(
                    Notebook.notebook_uuid == correct_notebook_uuid
                ).first()

                if correct_notebook and correct_notebook.id != notebook.id:
                    print(f"      → Moving {page.page_uuid[:8]}... to '{correct_notebook.visible_name}' (page {correct_page_number})")

                    if not dry_run:
                        page.notebook_id = correct_notebook.id
                        page.page_number = correct_page_number
                        moved_pages += 1
                        updates_count += 1
            else:
                # Page not found in any .content file - it's truly orphaned
                print(f"      ⚠️  {page.page_uuid[:8]}... not found in any .content file (keeping for now)")

    if not dry_run and updates_count > 0:
        db.commit()
        msg = f"   ✅ Updated {updates_count} pages"
        if moved_pages > 0:
            msg += f" ({moved_pages} moved to correct notebooks)"
        print(msg)
    elif dry_run and updates_count > 0:
        msg = f"   🔍 DRY RUN: Would update {updates_count} pages"
        if moved_pages > 0:
            msg += f" ({moved_pages} would be moved)"
        print(msg)
    else:
        print("   ✓ All pages already in correct order")


def main():
    parser = argparse.ArgumentParser(
        description="Fix page ordering based on .content files"
    )
    parser.add_argument(
        "--remarkable-dir",
        required=True,
        help="Path to reMarkable desktop sync folder"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be changed without making changes"
    )
    parser.add_argument(
        "--notebook-uuid",
        help="Only fix a specific notebook (by UUID)"
    )

    args = parser.parse_args()

    # Expand user path
    remarkable_dir = Path(args.remarkable_dir).expanduser()

    if not remarkable_dir.exists():
        print(f"❌ Error: {remarkable_dir} does not exist")
        sys.exit(1)

    print("=" * 70)
    print("  📚 Fix Page Ordering from .content Files")
    print("=" * 70)
    print()

    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made")
        print()

    # Connect to database
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        # Find all .content files
        content_files = list(remarkable_dir.glob("*.content"))

        print(f"📁 Found {len(content_files)} .content files in {remarkable_dir}")
        print()

        # Build a global map of page_uuid -> (notebook_uuid, page_number)
        print("🗺️  Building page-to-notebook map from all .content files...")
        page_to_notebook_map = build_content_map(remarkable_dir)
        print(f"   Found {len(page_to_notebook_map)} pages across all notebooks")
        print()

        if args.notebook_uuid:
            # Filter to specific notebook
            content_files = [
                f for f in content_files
                if f.stem == args.notebook_uuid
            ]
            if not content_files:
                print(f"❌ .content file for notebook {args.notebook_uuid} not found")
                sys.exit(1)
            print(f"🎯 Fixing only notebook: {args.notebook_uuid}")
            print()

        # Process each .content file
        total_fixed = 0

        for content_file in content_files:
            notebook_uuid = content_file.stem  # UUID is the filename

            try:
                content_data = parse_content_file(content_file)

                # Only process if fileType is notebook or epub
                file_type = content_data.get('fileType', '')
                if file_type not in ['notebook', 'epub']:
                    # Skip PDFs and folders
                    continue

                fix_notebook_pages(
                    db,
                    notebook_uuid,
                    content_data,
                    page_to_notebook_map,
                    dry_run=args.dry_run
                )
                total_fixed += 1

            except Exception as e:
                print(f"  ❌ Error processing {notebook_uuid}: {e}")
                continue

        print()
        print("=" * 70)

        if args.dry_run:
            print(f"  🔍 Dry run complete - {total_fixed} notebooks would be fixed")
        else:
            print(f"  ✅ Fixed page ordering for {total_fixed} notebooks")

        print("=" * 70)

    finally:
        db.close()


if __name__ == "__main__":
    main()
