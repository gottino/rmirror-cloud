#!/usr/bin/env python3
"""Fill in the written date of existing todos from their page's OCR text.

Todos extracted before the page date was read have no ``date_extracted``.
This sets it from the page's ``Date: dd-mm-yyyy`` line (the same parser the
extraction uses) and queues the changed todos for the user's todo targets,
so Notion's "Date Written" is filled by the sync worker. Only empty dates
are set; nothing else about a todo changes, and pages are not re-extracted.

Dry run by default:

    poetry run python scripts/backfill_todo_dates.py           # report only
    poetry run python scripts/backfill_todo_dates.py --apply   # write and queue
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session  # noqa: E402

from app.models.page import Page  # noqa: E402
from app.models.todo import Todo  # noqa: E402
from app.processors.todo_extractor import (  # noqa: E402
    _queue_todos_for_sync,
    extract_page_date,
)


def backfill(db: Session, apply: bool) -> dict:
    """Set missing todo dates from page text. Returns counts."""
    todos = (
        db.query(Todo)
        .filter(Todo.date_extracted.is_(None), Todo.page_id.isnot(None))
        .all()
    )
    by_page: dict[int, list[Todo]] = defaultdict(list)
    for todo in todos:
        by_page[todo.page_id].append(todo)

    counts = {"todos_without_date": len(todos), "pages": len(by_page), "dated": 0, "pages_dated": 0}
    dated_pages: list[Page] = []
    for page_id, page_todos in by_page.items():
        page = db.get(Page, page_id)
        page_date = extract_page_date(page.ocr_text if page else None)
        if page_date is None:
            continue
        counts["pages_dated"] += 1
        counts["dated"] += len(page_todos)
        if apply:
            for todo in page_todos:
                todo.date_extracted = page_date
            dated_pages.append(page)

    if apply and dated_pages:
        db.commit()
        for page in dated_pages:
            notebook = page.notebook
            user_id = notebook.user_id if notebook else None
            if user_id is not None:
                _queue_todos_for_sync(db, user_id, page, notebook)
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the dates and queue the syncs")
    args = parser.parse_args(argv)

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        counts = backfill(db, apply=args.apply)
    finally:
        db.close()

    verb = "Set" if args.apply else "Would set"
    print(
        f"{counts['todos_without_date']} todos without a date on {counts['pages']} pages; "
        f"{verb} the date of {counts['dated']} todos on {counts['pages_dated']} dated pages."
    )
    if not args.apply:
        print("Dry run: nothing written. Run again with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
