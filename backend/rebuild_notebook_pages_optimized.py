#!/usr/bin/env python3
"""
Optimized rebuild of notebook_pages mapping table from .content files.

This version uses bulk SQL statements - one per notebook instead of one per page.
Only processes actual notebooks (not PDFs or EPUBs).

Usage:
    poetry run python rebuild_notebook_pages_optimized.py --remarkable-dir "~/Library/Containers/..."
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Load environment variables
load_dotenv(Path(__file__).parent / '.env')

# Get database URL from environment
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("❌ DATABASE_URL not found in environment")
    sys.exit(1)


def parse_content_file(content_path: Path) -> dict:
    """Parse a .content file and return its contents."""
    with open(content_path, 'r') as f:
        return json.load(f)


def rebuild_notebook_mapping_bulk(db, notebook_uuid: str, content_data: dict, dry_run: bool = False):
    """Rebuild the notebook_pages mapping for a single notebook using a single SQL statement."""

    # Get the pages array from .content file
    content_pages = content_data.get('pages', [])

    # If pages is empty, try cPages.pages (newer format)
    if not content_pages and 'cPages' in content_data:
        c_pages = content_data['cPages'].get('pages', [])
        content_pages = [p['id'] for p in c_pages if isinstance(p, dict) and 'id' in p]

    if not content_pages:
        page_count = content_data.get('pageCount', 0)
        print(f"  ⏭️  Skipping {notebook_uuid}: no pages in .content (pageCount={page_count})")
        return 0

    # Build a single SQL statement that:
    # 1. Deletes old mappings for this notebook
    # 2. Inserts new mappings based on .content file

    # First, get notebook info
    result = db.execute(
        text("SELECT id, visible_name FROM notebooks WHERE notebook_uuid = :uuid"),
        {"uuid": notebook_uuid}
    ).fetchone()

    if not result:
        print(f"  ⚠️  Notebook {notebook_uuid} not found in database - skipping")
        return 0

    notebook_id, visible_name = result
    print(f"📓 {visible_name}")
    print(f"   UUID: {notebook_uuid}")
    print(f"   .content has {len(content_pages)} pages")

    if dry_run:
        print(f"   🔍 DRY RUN: Would rebuild {len(content_pages)} mappings")
        return len(content_pages)

    # Delete existing mappings for this notebook
    db.execute(
        text("DELETE FROM notebook_pages WHERE notebook_id = :notebook_id"),
        {"notebook_id": notebook_id}
    )

    # Build bulk INSERT with VALUES for all pages at once
    # We'll use a CTE to match page_uuids to page_ids
    if len(content_pages) > 0:
        # Build the VALUES clause for all pages
        values_parts = []
        for idx, page_uuid in enumerate(content_pages):
            page_number = idx + 1
            values_parts.append(f"('{page_uuid}', {page_number})")

        values_clause = ",\n    ".join(values_parts)

        # Single INSERT statement using a subquery to find matching pages
        sql = f"""
        INSERT INTO notebook_pages (notebook_id, page_id, page_number, created_at, updated_at)
        SELECT
            :notebook_id,
            p.id,
            v.page_number,
            NOW(),
            NOW()
        FROM (VALUES
            {values_clause}
        ) AS v(page_uuid, page_number)
        JOIN pages p ON p.page_uuid = v.page_uuid AND p.notebook_id = :notebook_id
        """

        result = db.execute(text(sql), {"notebook_id": notebook_id})
        pages_mapped = result.rowcount

        db.commit()

        print(f"   ✅ Created {pages_mapped} mappings")

        if pages_mapped < len(content_pages):
            missing = len(content_pages) - pages_mapped
            print(f"   ⚠️  {missing} pages from .content not found in database")

        return pages_mapped

    return 0


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Rebuild notebook_pages mapping table from .content files (notebooks only)"
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

    args = parser.parse_args()

    # Expand user path
    remarkable_dir = Path(args.remarkable_dir).expanduser()

    if not remarkable_dir.exists():
        print(f"❌ Error: {remarkable_dir} does not exist")
        sys.exit(1)

    print("=" * 70)
    print("  📚 Rebuild notebook_pages Mapping (Optimized - Notebooks Only)")
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

        # Process each .content file
        total_rebuilt = 0
        total_pages_mapped = 0

        for content_file in content_files:
            notebook_uuid = content_file.stem  # UUID is the filename

            try:
                content_data = parse_content_file(content_file)

                # Only process notebooks (skip PDFs and EPUBs)
                file_type = content_data.get('fileType', '')
                if file_type not in ['notebook', '']:
                    # Skip PDFs and EPUBs
                    continue

                pages_mapped = rebuild_notebook_mapping_bulk(
                    db,
                    notebook_uuid,
                    content_data,
                    dry_run=args.dry_run
                )

                if pages_mapped > 0:
                    total_rebuilt += 1
                    total_pages_mapped += pages_mapped

            except Exception as e:
                print(f"  ❌ Error processing {notebook_uuid}: {e}")
                import traceback
                traceback.print_exc()
                continue

        print()
        print("=" * 70)

        if args.dry_run:
            print("  🔍 Dry run complete")
        else:
            print(f"  ✅ Rebuilt mappings for {total_rebuilt} notebooks")
            print(f"  ✅ Total pages mapped: {total_pages_mapped}")

        print("=" * 70)

    finally:
        db.close()


if __name__ == "__main__":
    main()
