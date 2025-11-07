#!/usr/bin/env python3
"""
Utility to rebuild full_path for notebooks based on parent_uuid relationships.

This script reconstructs the folder hierarchy by walking up the parent chain
and building the full path for each notebook/folder.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.notebook import Notebook


def build_path_for_notebook(session: Session, notebook: Notebook, visited: set = None) -> str:
    """
    Recursively build the full path for a notebook by walking up the parent chain.

    Args:
        session: Database session
        notebook: Notebook to build path for
        visited: Set of visited UUIDs to prevent infinite loops

    Returns:
        Full path string like "Archive/Doodle/Reset"
    """
    if visited is None:
        visited = set()

    # Prevent infinite loops
    if notebook.notebook_uuid in visited:
        return notebook.visible_name

    visited.add(notebook.notebook_uuid)

    # If no parent, this is a root item
    if not notebook.parent_uuid:
        return notebook.visible_name

    # Find parent
    parent = session.query(Notebook).filter(
        Notebook.notebook_uuid == notebook.parent_uuid,
        Notebook.user_id == notebook.user_id
    ).first()

    if not parent:
        # Parent not found, just return visible name
        return notebook.visible_name

    # Recursively build parent path
    parent_path = build_path_for_notebook(session, parent, visited)

    # Combine parent path with current name
    return f"{parent_path}/{notebook.visible_name}"


def rebuild_all_paths(db_path: str, user_id: int = None):
    """
    Rebuild full_path for all notebooks in the database.

    Args:
        db_path: Path to SQLite database
        user_id: Optional user ID to filter (None = all users)
    """
    print("="*60)
    print("Rebuilding Folder Paths")
    print("="*60)

    engine = create_engine(f"sqlite:///{db_path}")
    session = Session(engine)

    try:
        # Get all notebooks
        query = session.query(Notebook)
        if user_id:
            query = query.filter(Notebook.user_id == user_id)

        notebooks = query.all()

        print(f"\n📊 Found {len(notebooks)} notebooks")
        print("\n🔄 Rebuilding paths...")

        updated_count = 0
        for notebook in notebooks:
            # Build path
            full_path = build_path_for_notebook(session, notebook)

            # Update if changed
            if notebook.full_path != full_path:
                notebook.full_path = full_path
                updated_count += 1

                if updated_count % 100 == 0:
                    print(f"  📊 Progress: {updated_count} paths updated...")

        # Commit changes
        session.commit()

        print(f"\n✅ Updated {updated_count} paths")
        print(f"✅ {len(notebooks) - updated_count} paths already correct")

        # Show some examples
        print("\n📁 Sample folder structure:")
        samples = session.query(Notebook).filter(
            Notebook.user_id == user_id if user_id else True,
            Notebook.full_path.isnot(None)
        ).order_by(Notebook.full_path).limit(10).all()

        for nb in samples:
            icon = "📁" if nb.document_type == "folder" else "📄"
            print(f"  {icon} {nb.full_path}")

        print("\n✅ Path rebuild complete!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        session.rollback()
        return 1

    finally:
        session.close()

    return 0


def main():
    """Run the path rebuild."""
    import argparse

    parser = argparse.ArgumentParser(description="Rebuild folder paths for notebooks")
    parser.add_argument("--db", default="rmirror.db", help="Path to database file")
    parser.add_argument("--user-id", type=int, help="User ID to filter (optional)")

    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        # Try relative to script
        db_path = Path(__file__).parent.parent / args.db

    if not db_path.exists():
        print(f"❌ Database not found: {args.db}")
        return 1

    print(f"📂 Database: {db_path}")
    if args.user_id:
        print(f"👤 User ID: {args.user_id}")
    else:
        print(f"👥 Processing all users")

    return rebuild_all_paths(str(db_path), args.user_id)


if __name__ == "__main__":
    sys.exit(main())
