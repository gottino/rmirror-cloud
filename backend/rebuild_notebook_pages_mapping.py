#!/usr/bin/env python3
"""
Rebuild notebook_pages Mapping Table from .content Files

This script reads all reMarkable .content files and rebuilds the notebook_pages
mapping table with the correct page-to-notebook relationships and ordering.

The .content file is the source of truth for which pages belong to which notebook
and in what order.

Usage:
    poetry run python rebuild_notebook_pages_mapping.py --remarkable-dir "~/Library/Containers/..."
"""

import json
import argparse
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import sys
import os
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
load_dotenv(Path(__file__).parent / '.env')

from app.models.notebook import Notebook
from app.models.notebook_page import NotebookPage
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


def rebuild_notebook_mapping(
    db,
    notebook_uuid: str,
    content_data: dict,
    dry_run: bool = False
):
    """Rebuild the notebook_pages mapping for a single notebook based on its .content file."""

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
        # Delete any existing mappings for this notebook
        if not dry_run:
            deleted = db.query(NotebookPage).filter(
                NotebookPage.notebook_id == notebook.id
            ).delete()
            if deleted > 0:
                print(f"     Deleted {deleted} orphan mappings")
        return

    print(f"\n📓 {notebook.visible_name}")
    print(f"   UUID: {notebook_uuid}")
    print(f"   .content has {len(content_pages)} pages")

    # Delete existing mappings for this notebook
    if not dry_run:
        deleted = db.query(NotebookPage).filter(
            NotebookPage.notebook_id == notebook.id
        ).delete()
        print(f"   🗑️  Deleted {deleted} old mappings")

    # Create new mappings from .content file
    pages_mapped = 0
    pages_missing = []

    for index, page_uuid in enumerate(content_pages):
        correct_page_number = index + 1  # 1-indexed

        # Find the page by UUID
        page = db.query(Page).filter(
            Page.page_uuid == page_uuid
        ).first()

        if page:
            if not dry_run:
                # Create new mapping
                mapping = NotebookPage(
                    notebook_id=notebook.id,
                    page_id=page.id,
                    page_number=correct_page_number
                )
                db.add(mapping)
                pages_mapped += 1
        else:
            pages_missing.append((correct_page_number, page_uuid))

    if not dry_run:
        db.commit()
        print(f"   ✅ Created {pages_mapped} new mappings")
    else:
        print(f"   🔍 DRY RUN: Would create {pages_mapped} mappings")

    if pages_missing:
        print(f"   ⚠️  {len(pages_missing)} pages in .content not found in database:")
        for page_num, page_uuid in pages_missing[:5]:  # Show first 5
            print(f"      - Page {page_num}: {page_uuid[:8]}...")
        if len(pages_missing) > 5:
            print(f"      ... and {len(pages_missing) - 5} more")


def main():
    parser = argparse.ArgumentParser(
        description="Rebuild notebook_pages mapping table from .content files"
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
        help="Only rebuild mapping for a specific notebook (by UUID)"
    )

    args = parser.parse_args()

    # Expand user path
    remarkable_dir = Path(args.remarkable_dir).expanduser()

    if not remarkable_dir.exists():
        print(f"❌ Error: {remarkable_dir} does not exist")
        sys.exit(1)

    print("=" * 70)
    print("  📚 Rebuild notebook_pages Mapping Table from .content Files")
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

        if args.notebook_uuid:
            # Filter to specific notebook
            content_files = [
                f for f in content_files
                if f.stem == args.notebook_uuid
            ]
            if not content_files:
                print(f"❌ .content file for notebook {args.notebook_uuid} not found")
                sys.exit(1)
            print(f"🎯 Rebuilding only notebook: {args.notebook_uuid}")
            print()

        # Process each .content file
        total_rebuilt = 0

        for content_file in content_files:
            notebook_uuid = content_file.stem  # UUID is the filename

            try:
                content_data = parse_content_file(content_file)

                # Only process if fileType is notebook or epub
                file_type = content_data.get('fileType', '')
                if file_type not in ['notebook', 'epub']:
                    # Skip PDFs and folders
                    continue

                rebuild_notebook_mapping(
                    db,
                    notebook_uuid,
                    content_data,
                    dry_run=args.dry_run
                )
                total_rebuilt += 1

            except Exception as e:
                print(f"  ❌ Error processing {notebook_uuid}: {e}")
                continue

        print()
        print("=" * 70)

        if args.dry_run:
            print(f"  🔍 Dry run complete - {total_rebuilt} notebooks would be rebuilt")
        else:
            print(f"  ✅ Rebuilt mappings for {total_rebuilt} notebooks")

        print("=" * 70)

    finally:
        db.close()


if __name__ == "__main__":
    main()
