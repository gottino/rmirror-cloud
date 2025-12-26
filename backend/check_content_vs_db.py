#!/usr/bin/env python3
"""Check consistency between .content files and database pages."""

import json
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models.notebook import Notebook
from app.models.page import Page


def check_content_vs_db(remarkable_source_dir: str):
    """Compare pages in .content files vs database."""
    settings = get_settings()
    source_path = Path(remarkable_source_dir)

    if not source_path.exists():
        print(f"ERROR: Source directory does not exist: {remarkable_source_dir}")
        sys.exit(1)

    # Create database session
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Get all handwritten notebooks
        notebooks = (
            db.query(Notebook)
            .filter(Notebook.document_type.in_(["notebook", "DocumentType"]))
            .all()
        )

        print(f"Found {len(notebooks)} handwritten notebooks\n")

        total_missing = 0
        total_extra = 0

        for notebook in notebooks:
            # Find .content file
            content_file = source_path / f"{notebook.notebook_uuid}.content"

            if not content_file.exists():
                print(f"⚠️  {notebook.visible_name} ({notebook.notebook_uuid}): No .content file")
                continue

            # Parse .content file
            with open(content_file, "r") as f:
                content_json = json.load(f)

            # Get pages from .content
            pages_array = content_json.get("pages", [])
            if not pages_array and "cPages" in content_json:
                c_pages = content_json["cPages"].get("pages", [])
                pages_array = [p["id"] for p in c_pages if isinstance(p, dict) and "id" in p]

            content_page_uuids = set(pages_array)

            # Get pages from database
            db_pages = db.query(Page).filter(Page.notebook_id == notebook.id).all()
            db_page_uuids = set(p.page_uuid for p in db_pages if p.page_uuid)

            # Compare
            missing_in_db = content_page_uuids - db_page_uuids
            extra_in_db = db_page_uuids - content_page_uuids

            if missing_in_db or extra_in_db:
                print(f"❌ {notebook.visible_name} ({notebook.notebook_uuid}):")
                print(f"   .content has {len(content_page_uuids)} pages")
                print(f"   Database has {len(db_page_uuids)} pages")

                if missing_in_db:
                    print(f"   Missing in DB: {len(missing_in_db)} pages")
                    # Check if files actually exist
                    notebook_dir = source_path / notebook.notebook_uuid
                    if notebook_dir.exists():
                        existing = 0
                        for uuid in list(missing_in_db)[:5]:  # Show first 5
                            rm_file = notebook_dir / f"{uuid}.rm"
                            if rm_file.exists():
                                existing += 1
                                print(f"      - {uuid} (.rm file EXISTS)")
                            else:
                                print(f"      - {uuid} (.rm file missing)")
                        if len(missing_in_db) > 5:
                            print(f"      ... and {len(missing_in_db) - 5} more")
                    total_missing += len(missing_in_db)

                if extra_in_db:
                    print(f"   Extra in DB: {len(extra_in_db)} pages")
                    for uuid in list(extra_in_db)[:3]:  # Show first 3
                        print(f"      - {uuid}")
                    if len(extra_in_db) > 3:
                        print(f"      ... and {len(extra_in_db) - 3} more")
                    total_extra += len(extra_in_db)

                print()
            else:
                print(f"✅ {notebook.visible_name}: {len(content_page_uuids)} pages (all match)")

        print(f"\n{'='*60}")
        print(f"Summary:")
        print(f"  Total pages missing in DB:  {total_missing}")
        print(f"  Total extra pages in DB:    {total_extra}")
        print(f"{'='*60}")

    finally:
        db.close()


if __name__ == "__main__":
    print("Checking .content files vs database pages...")
    print()

    default_source = "/Users/gabriele/Library/Containers/com.remarkable.desktop/Data/Library/Application Support/remarkable/desktop"
    source_dir = sys.argv[1] if len(sys.argv) > 1 else default_source

    check_content_vs_db(source_dir)
