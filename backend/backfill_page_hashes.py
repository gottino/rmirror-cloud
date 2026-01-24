#!/usr/bin/env python3
"""Backfill file hashes for existing pages to prevent re-OCR'ing."""

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


def backfill_hashes(remarkable_source_dir: str):
    """Backfill file hashes for pages without them."""
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
        # Find pages without file_hash, updated before Dec 1, 2025
        # Only process handwritten notebooks (not PDFs/EPUBs)
        cutoff_date = datetime(2025, 12, 1)
        pages = (
            db.query(Page)
            .join(Notebook, Page.notebook_id == Notebook.id)
            .filter(
                Page.file_hash.is_(None),
                Page.updated_at < cutoff_date,
                Page.page_uuid.isnot(None),
                Notebook.notebook_uuid.isnot(None),
                Notebook.document_type.in_(["notebook", "DocumentType"]),  # Only handwritten notebooks
            )
            .all()
        )

        total = len(pages)
        print(f"Found {total} pages without file_hash (updated before {cutoff_date})")

        if total == 0:
            print("No pages to update!")
            return

        updated = 0
        skipped = 0
        errors = 0

        for i, page in enumerate(pages, 1):
            try:
                # Get notebook to find the .rm file
                notebook = db.query(Notebook).filter(Notebook.id == page.notebook_id).first()
                if not notebook:
                    print(f"[{i}/{total}] Page {page.id}: SKIP (no notebook)")
                    skipped += 1
                    continue

                # Construct path to .rm file
                rm_file_path = source_path / notebook.notebook_uuid / f"{page.page_uuid}.rm"

                print(f"[{i}/{total}] Page {page.id} ({notebook.notebook_uuid}/{page.page_uuid}.rm)...", end=" ")

                # Check if file exists
                if not rm_file_path.exists():
                    print("SKIP (file not found)")
                    skipped += 1
                    continue

                # Read file and calculate hash
                file_bytes = rm_file_path.read_bytes()
                file_stream = BytesIO(file_bytes)
                file_hash = calculate_file_hash(file_stream)

                # Update page
                page.file_hash = file_hash
                db.commit()

                print(f"OK (hash: {file_hash[:16]}...)")
                updated += 1

                # Progress update every 100 pages
                if i % 100 == 0:
                    print(f"\n=== Progress: {i}/{total} ({updated} updated, {skipped} skipped, {errors} errors) ===\n")

            except Exception as e:
                print(f"ERROR: {e}")
                errors += 1
                db.rollback()
                continue

        print(f"\n{'='*60}")
        print("Backfill complete!")
        print(f"  Total pages:   {total}")
        print(f"  Updated:       {updated}")
        print(f"  Skipped:       {skipped}")
        print(f"  Errors:        {errors}")
        print(f"{'='*60}")

    finally:
        db.close()


if __name__ == "__main__":
    print("Starting page hash backfill...")
    print("This will calculate file hashes for all pages without them.")
    print()

    # Default reMarkable source directory
    default_source = "/Users/gabriele/Library/Containers/com.remarkable.desktop/Data/Library/Application Support/remarkable/desktop"
    source_dir = sys.argv[1] if len(sys.argv) > 1 else default_source

    backfill_hashes(source_dir)
