#!/usr/bin/env python3
"""Backfill file hashes based on notebook metadata lastModified timestamp."""

import json
import sys
from datetime import datetime
from io import BytesIO
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models.notebook import Notebook
from app.models.page import Page
from app.utils.files import calculate_file_hash


def backfill_by_metadata(remarkable_source_dir: str):
    """Backfill file hashes for notebooks modified before Dec 1, 2025."""
    settings = get_settings()
    source_path = Path(remarkable_source_dir)

    if not source_path.exists():
        print(f"ERROR: Source directory does not exist: {remarkable_source_dir}")
        sys.exit(1)

    print(f"Using reMarkable source directory: {source_path}")

    # Create database session
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Cutoff date: December 1, 2025
        cutoff_timestamp = int(datetime(2025, 12, 1).timestamp() * 1000)  # Convert to milliseconds

        # Get all handwritten notebooks
        notebooks = (
            db.query(Notebook)
            .filter(Notebook.document_type.in_(["notebook", "DocumentType"]))
            .all()
        )

        print(f"Found {len(notebooks)} handwritten notebooks")
        print(f"Cutoff date: December 1, 2025 (timestamp: {cutoff_timestamp})")
        print()

        notebooks_to_process = []

        # Find notebooks with lastModified before cutoff
        for notebook in notebooks:
            metadata_file = source_path / f"{notebook.notebook_uuid}.metadata"

            if not metadata_file.exists():
                continue

            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)

                last_modified = metadata.get('lastModified')

                if last_modified:
                    # Convert string to int if needed
                    if isinstance(last_modified, str):
                        last_modified = int(last_modified)

                    if last_modified <= cutoff_timestamp:
                        notebooks_to_process.append((notebook, last_modified))
            except Exception as e:
                print(f"⚠️  Error reading metadata for {notebook.visible_name}: {e}")
                continue

        print(f"Found {len(notebooks_to_process)} notebooks modified before Dec 1, 2025")
        print()

        total_updated = 0
        total_skipped = 0
        total_errors = 0
        notebook_stats = []

        for notebook, last_modified in notebooks_to_process:
            # Get pages for this notebook that don't have hashes
            pages = (
                db.query(Page)
                .filter(
                    Page.notebook_id == notebook.id,
                    Page.file_hash.is_(None),
                    Page.page_uuid.isnot(None)
                )
                .all()
            )

            if not pages:
                continue

            print(f"Processing {notebook.visible_name} ({len(pages)} pages without hash)...")

            updated = 0
            skipped = 0
            errors = 0

            for page in pages:
                try:
                    # Construct path to .rm file
                    rm_file_path = source_path / notebook.notebook_uuid / f"{page.page_uuid}.rm"

                    if not rm_file_path.exists():
                        skipped += 1
                        continue

                    # Read file and calculate hash
                    file_bytes = rm_file_path.read_bytes()
                    file_stream = BytesIO(file_bytes)
                    file_hash = calculate_file_hash(file_stream)

                    # Update page
                    page.file_hash = file_hash
                    db.commit()
                    updated += 1

                except Exception as e:
                    print(f"  ERROR on page {page.page_uuid}: {e}")
                    errors += 1
                    db.rollback()
                    continue

            print(f"  ✓ Updated {updated}, Skipped {skipped}, Errors {errors}")

            total_updated += updated
            total_skipped += skipped
            total_errors += errors

            notebook_stats.append({
                'name': notebook.visible_name,
                'updated': updated,
                'skipped': skipped,
                'errors': errors
            })

        print()
        print('='*80)
        print('Backfill Summary')
        print('='*80)
        print(f"Total pages updated: {total_updated}")
        print(f"Total pages skipped: {total_skipped}")
        print(f"Total errors: {total_errors}")
        print()

        # Now generate report of remaining unhashed pages by notebook
        print('='*100)
        print('Remaining Unhashed Pages by Notebook')
        print('='*100)
        print()

        all_notebooks = (
            db.query(Notebook)
            .filter(Notebook.document_type.in_(["notebook", "DocumentType"]))
            .order_by(Notebook.visible_name)
            .all()
        )

        remaining_report = []
        total_remaining = 0

        for notebook in all_notebooks:
            # Skip QuickSheets
            if notebook.visible_name.lower() == 'quick sheets':
                continue

            unhashed_count = (
                db.query(Page)
                .filter(
                    Page.notebook_id == notebook.id,
                    Page.file_hash.is_(None)
                )
                .count()
            )

            if unhashed_count > 0:
                # Get lastModified from metadata
                metadata_file = source_path / f"{notebook.notebook_uuid}.metadata"
                last_modified_str = "N/A"

                if metadata_file.exists():
                    try:
                        with open(metadata_file, 'r') as f:
                            metadata = json.load(f)

                        last_modified = metadata.get('lastModified')
                        if last_modified:
                            if isinstance(last_modified, str):
                                last_modified = int(last_modified)

                            # Convert timestamp to readable date
                            last_modified_dt = datetime.fromtimestamp(last_modified / 1000)
                            last_modified_str = last_modified_dt.strftime('%Y-%m-%d %H:%M')
                    except Exception:
                        pass

                remaining_report.append((notebook.visible_name, unhashed_count, last_modified_str))
                total_remaining += unhashed_count

        if remaining_report:
            print(f"{'Notebook':<40} {'Unhashed Pages':>15} {'Last Modified':>25}")
            print('-'*100)
            for name, count, last_modified in remaining_report:
                print(f"{name[:40]:<40} {count:>15} {last_modified:>25}")
            print('-'*100)
            print(f"{'TOTAL':<40} {total_remaining:>15}")
        else:
            print("✓ All pages have hashes!")

        print()
        print('='*100)

    finally:
        db.close()


if __name__ == "__main__":
    print("Starting metadata-based hash backfill...")
    print("Processing notebooks modified before December 1, 2025")
    print()

    # Default reMarkable source directory
    default_source = "/Users/gabriele/Library/Containers/com.remarkable.desktop/Data/Library/Application Support/remarkable/desktop"
    source_dir = sys.argv[1] if len(sys.argv) > 1 else default_source

    backfill_by_metadata(source_dir)
