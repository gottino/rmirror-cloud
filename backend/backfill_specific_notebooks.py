#!/usr/bin/env python3
"""Backfill file hashes for specific notebooks."""

import sys
from io import BytesIO
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models.notebook import Notebook
from app.models.notebook_page import NotebookPage
from app.models.page import Page
from app.utils.files import calculate_file_hash


def backfill_specific_notebooks(remarkable_source_dir: str):
    """Backfill file hashes for specific notebooks."""
    settings = get_settings()
    source_path = Path(remarkable_source_dir)

    if not source_path.exists():
        print(f"ERROR: Source directory does not exist: {remarkable_source_dir}")
        sys.exit(1)

    print(f"Using reMarkable source directory: {source_path}")
    print()

    # Create database session
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Notebooks to fully backfill
        full_backfill = ["Collaboration", "Axpo", "Markus", "Marton", "Alex", "Christian"]

        # Special handling for Yannick (only pages 1-75)
        yannick_max_page = 75

        print("=" * 80)
        print("Targeted Notebook Backfill")
        print("=" * 80)
        print()
        print("Full backfill: Collaboration, Axpo, Markus, Marton, Alex, Christian")
        print("Partial backfill: Yannick (pages 1-75 only)")
        print()

        total_updated = 0
        total_skipped = 0
        total_errors = 0

        # Process full backfill notebooks
        for notebook_name in full_backfill:
            notebook = (
                db.query(Notebook)
                .filter(
                    Notebook.visible_name == notebook_name,
                    Notebook.document_type.in_(["notebook", "DocumentType"])
                )
                .first()
            )

            if not notebook:
                print(f"⚠️  Notebook '{notebook_name}' not found")
                continue

            # Get pages without hashes
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
                print(f"✓ {notebook_name}: No unhashed pages")
                continue

            print(f"Processing {notebook_name} ({len(pages)} pages without hash)...")

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

        # Special handling for Yannick (pages 1-75 only)
        notebook = (
            db.query(Notebook)
            .filter(
                Notebook.visible_name == "Yannick",
                Notebook.document_type.in_(["notebook", "DocumentType"])
            )
            .first()
        )

        if notebook:
            print(f"Processing Yannick (pages 1-{yannick_max_page} only)...")

            # Get pages with their page numbers via NotebookPage
            pages_query = (
                db.query(Page, NotebookPage.page_number)
                .join(NotebookPage, Page.id == NotebookPage.page_id)
                .filter(
                    NotebookPage.notebook_id == notebook.id,
                    Page.file_hash.is_(None),
                    Page.page_uuid.isnot(None),
                    NotebookPage.page_number <= yannick_max_page
                )
                .all()
            )

            if pages_query:
                print(f"  Found {len(pages_query)} unhashed pages (numbered 1-{yannick_max_page})")

                updated = 0
                skipped = 0
                errors = 0

                for page, page_number in pages_query:
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
            else:
                print(f"  ✓ No unhashed pages found in range 1-{yannick_max_page}")
        else:
            print("⚠️  Notebook 'Yannick' not found")

        print()
        print("=" * 80)
        print("Backfill Summary")
        print("=" * 80)
        print(f"Total pages updated: {total_updated}")
        print(f"Total pages skipped: {total_skipped}")
        print(f"Total errors: {total_errors}")
        print()

        # Report remaining unhashed pages
        print("=" * 80)
        print("Remaining Unhashed Pages")
        print("=" * 80)

        all_target_notebooks = full_backfill + ["Yannick"]

        for notebook_name in all_target_notebooks:
            notebook = (
                db.query(Notebook)
                .filter(
                    Notebook.visible_name == notebook_name,
                    Notebook.document_type.in_(["notebook", "DocumentType"])
                )
                .first()
            )

            if notebook:
                unhashed_count = (
                    db.query(Page)
                    .filter(
                        Page.notebook_id == notebook.id,
                        Page.file_hash.is_(None)
                    )
                    .count()
                )

                if unhashed_count > 0:
                    print(f"  {notebook_name}: {unhashed_count} pages")

        print("=" * 80)

    finally:
        db.close()


if __name__ == "__main__":
    print("Starting targeted notebook backfill...")
    print()

    # Default reMarkable source directory
    default_source = "/Users/gabriele/Library/Containers/com.remarkable.desktop/Data/Library/Application Support/remarkable/desktop"
    source_dir = sys.argv[1] if len(sys.argv) > 1 else default_source

    backfill_specific_notebooks(source_dir)
