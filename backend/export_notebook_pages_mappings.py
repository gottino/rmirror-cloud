#!/usr/bin/env python3
"""
Export notebook_pages mappings from local database to SQL file for production import.

This script exports the notebook_pages mappings for a specific user so they can be
imported into the production database.

Usage:
    poetry run python export_notebook_pages_mappings.py --email gabriele.ottino@me.com --output mappings.sql
"""

import argparse
import sys
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv(Path(__file__).parent / '.env')

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.models.user import User
from app.models.notebook import Notebook
from app.models.notebook_page import NotebookPage
from app.models.page import Page

# Get database URL from environment
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./rmirror.db')


def export_mappings(user_email: str, output_file: Path):
    """Export notebook_pages mappings for a user to a SQL file."""

    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        # Find the user
        user = db.query(User).filter(User.email == user_email).first()

        if not user:
            print(f"❌ User not found: {user_email}")
            return False

        print(f"✓ Found user: {user.email} (ID: {user.id})")
        print()

        # Get all notebooks for this user
        notebooks = db.query(Notebook).filter(Notebook.user_id == user.id).all()
        print(f"📚 Found {len(notebooks)} notebooks")

        # Get all notebook_pages mappings for this user's notebooks
        notebook_ids = [nb.id for nb in notebooks]

        if not notebook_ids:
            print("⚠️  No notebooks found for this user")
            return False

        mappings = (
            db.query(NotebookPage, Notebook, Page)
            .join(Notebook, NotebookPage.notebook_id == Notebook.id)
            .join(Page, NotebookPage.page_id == Page.id)
            .filter(Notebook.user_id == user.id)
            .order_by(Notebook.notebook_uuid, NotebookPage.page_number)
            .all()
        )

        print(f"📄 Found {len(mappings)} page mappings")
        print()

        # Generate SQL INSERT statements
        with open(output_file, 'w') as f:
            f.write("-- Notebook Pages Mappings Export\n")
            f.write(f"-- User: {user_email}\n")
            f.write(f"-- Date: {Path(__file__).stat().st_mtime}\n")
            f.write("-- \n")
            f.write("-- INSTRUCTIONS:\n")
            f.write("-- 1. SSH into production server\n")
            f.write("-- 2. Run: psql -U rmirror -d rmirror -f mappings.sql\n")
            f.write("-- \n\n")

            f.write("BEGIN;\n\n")

            # Group by notebook for better readability
            current_notebook_uuid = None

            for mapping, notebook, page in mappings:
                if notebook.notebook_uuid != current_notebook_uuid:
                    current_notebook_uuid = notebook.notebook_uuid
                    f.write(f"\n-- Notebook: {notebook.visible_name} ({notebook.notebook_uuid})\n")

                # Generate INSERT using UUIDs to match across databases
                # Use LIMIT 1 to handle duplicate pages with same UUID
                sql = (
                    f"INSERT INTO notebook_pages (notebook_id, page_id, page_number, created_at, updated_at)\n"
                    f"SELECT \n"
                    f"  (SELECT id FROM notebooks WHERE notebook_uuid = '{notebook.notebook_uuid}' LIMIT 1),\n"
                    f"  (SELECT id FROM pages WHERE page_uuid = '{page.page_uuid}' AND notebook_id = (SELECT id FROM notebooks WHERE notebook_uuid = '{notebook.notebook_uuid}' LIMIT 1) LIMIT 1),\n"
                    f"  {mapping.page_number},\n"
                    f"  NOW(),\n"
                    f"  NOW()\n"
                    f"WHERE EXISTS (SELECT 1 FROM notebooks WHERE notebook_uuid = '{notebook.notebook_uuid}')\n"
                    f"  AND EXISTS (SELECT 1 FROM pages WHERE page_uuid = '{page.page_uuid}' AND notebook_id = (SELECT id FROM notebooks WHERE notebook_uuid = '{notebook.notebook_uuid}' LIMIT 1))\n"
                    f"ON CONFLICT DO NOTHING;\n"
                )
                f.write(sql)

            f.write("\nCOMMIT;\n")

        print(f"✅ Exported {len(mappings)} mappings to: {output_file}")
        print()
        print("Next steps:")
        print(f"  1. Copy file to production: scp {output_file} deploy@167.235.74.51:/tmp/")
        print(f"  2. SSH to production: ssh deploy@167.235.74.51")
        print(f"  3. Run SQL: psql -U rmirror -d rmirror -f /tmp/{output_file.name}")

        return True

    finally:
        db.close()


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Export notebook_pages mappings for a user"
    )
    parser.add_argument(
        "--email",
        required=True,
        help="User email address"
    )
    parser.add_argument(
        "--output",
        default="notebook_pages_mappings.sql",
        help="Output SQL file (default: notebook_pages_mappings.sql)"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("  📤 Export Notebook Pages Mappings")
    print("=" * 70)
    print()

    output_file = Path(args.output)

    success = export_mappings(args.email, output_file)

    print()
    print("=" * 70)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
