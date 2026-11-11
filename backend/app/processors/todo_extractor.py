"""
Todo extraction from OCR text.

Extracts todo items from handwritten notes by detecting checkbox patterns.
"""

import logging
import re
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.notebook import Notebook
from app.models.notebook_page import NotebookPage
from app.models.page import OcrStatus, Page
from app.models.todo import REMOVED_BY_USER, REMOVED_FROM_PAGE, Todo
from app.processors.intelligent_todo_deduplication import (
    IntelligentTodoDeduplicator,
    TodoCandidate,
    create_todo_candidate,
)
from app.services.sync_queue import enabled_todo_targets, queue_todo_sync

logger = logging.getLogger(__name__)


def extract_todos_from_text(
    text: str, notebook_id: int, page_number: int, page_id: Optional[int] = None
) -> List[TodoCandidate]:
    """
    Extract todo items from OCR text.

    Args:
        text: OCR text from a page
        notebook_id: Database ID of the notebook
        page_number: Page number
        page_id: Database ID of the page

    Returns:
        List of TodoCandidate objects
    """
    if not text or not text.strip():
        return []

    todos = []
    lines = text.split("\n")

    # Todo patterns: (pattern, completed_status)
    todo_patterns = [
        # Markdown-style checkboxes (what Claude Vision outputs)
        (r"^\s*-\s*\[\s*\]\s*(.+)", False),  # - [ ] task
        (r"^\s*-\s*\[x\]\s*(.+)", True),  # - [x] task
        (r"^\s*-\s*\[X\]\s*(.+)", True),  # - [X] task
        (r"^\s*-\s*\[✓\]\s*(.+)", True),  # - [✓] task
        (r"^\s*-\s*\[☑\]\s*(.+)", True),  # - [☑] task
        # Unicode checkbox symbols
        (r"^\s*-?\s*☐\s*(.+)", False),  # ☐ task
        (r"^\s*-?\s*☑\s*(.+)", True),  # ☑ task
        (r"^\s*-?\s*✓\s*(.+)", True),  # ✓ task
        (r"^\s*-?\s*□\s*(.+)", False),  # □ task
    ]

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # Skip lines that start with curved arrows (sub-points, not tasks)
        if line_stripped.startswith("↳") or line_stripped.startswith("- ↳"):
            continue

        # Check each pattern
        for pattern, completed in todo_patterns:
            match = re.match(pattern, line_stripped, re.IGNORECASE)
            if match:
                todo_text = match.group(1).strip()
                # Filter out very short matches
                if todo_text and len(todo_text) > 2:
                    todo = create_todo_candidate(
                        text=todo_text,
                        notebook_id=notebook_id,
                        page_number=page_number,
                        page_id=page_id,
                        confidence=1.0,  # High confidence from Claude Vision
                        completed=completed,
                    )
                    todos.append(todo)
                break  # Don't match multiple patterns for same line

    return todos


def process_page_todos(
    db: Session, page: Page, user_id: int, force_reprocess: bool = False
) -> int:
    """
    Extract a page's todos, store them, and queue them for the todo targets.

    Idempotent: running it again on the same text changes nothing. Against
    the page's stored todos (``IntelligentTodoDeduplicator``):

    - a new line creates a todo;
    - a matched line (similar text, see the de-duplicator) keeps its todo and
      the todo takes the line's current text; a checked box marks it
      completed (the page never reopens a todo: unchecking is done in the
      dashboard);
    - a stored todo no line matches (``todos_to_delete``) is marked removed
      (REMOVED_FROM_PAGE) and comes back if the line does. Its task in
      Todoist / Notion is left as it is: nothing is deleted remotely.
    - a todo the user deleted in the dashboard (REMOVED_BY_USER) stays removed.

    Changed and new todos are queued for the user's enabled todo targets
    (none queued without one). Makes no external calls.

    Args:
        db: Database session
        page: Page object to process
        user_id: User ID for the todos
        force_reprocess: If False, a page that already has todos is skipped

    Returns:
        Number of todos created, changed or removed
    """
    if not page.ocr_text or not page.ocr_text.strip():
        logger.debug(f"Page {page.id} has no OCR text, skipping todo extraction")
        return 0

    existing_todos = (
        db.query(Todo)
        .filter(Todo.page_id == page.id, Todo.user_id == user_id)
        .all()
    )
    if existing_todos and not force_reprocess:
        logger.debug(f"Page {page.id} already has {len(existing_todos)} todos, skipping")
        return 0

    notebook_page = (
        db.query(NotebookPage)
        .filter(NotebookPage.page_id == page.id)
        .first()
    )
    page_number = notebook_page.page_number if notebook_page else 0
    notebook = page.notebook

    new_todos = extract_todos_from_text(
        text=page.ocr_text,
        notebook_id=page.notebook_id,
        page_number=page_number,
        page_id=page.id,
    )
    if not new_todos and not existing_todos:
        return 0

    # Stored todos belong to this page (page_id), so they are compared at the
    # page's current number even if pages were reordered since.
    by_id = {todo.id: todo for todo in existing_todos}
    existing_todos_dict = [
        {
            "id": todo.id,
            "text": todo.text,
            "confidence": todo.confidence or 1.0,
            "page_number": page_number,
            "completed": todo.completed,
            "bounding_box": todo.bounding_box,
        }
        for todo in existing_todos
    ]

    deduplicator = IntelligentTodoDeduplicator(
        similarity_threshold=0.8,
        position_threshold=50.0,
        confidence_improvement_threshold=0.1,
    )
    final_todos, todos_to_delete = deduplicator.deduplicate_todos_for_page(
        new_todos, existing_todos_dict
    )

    now = datetime.utcnow()
    changed = 0
    for candidate in final_todos:
        todo = by_id.get(candidate.existing_id) if candidate.existing_id else None
        if todo is None:
            db.add(
                Todo(
                    user_id=user_id,
                    notebook_id=candidate.notebook_id,
                    page_id=candidate.page_id,
                    page_number=candidate.page_number,
                    page_uuid=page.page_uuid if page.page_uuid else None,
                    title=candidate.text[:200],
                    text=candidate.text,
                    completed=candidate.completed,
                    confidence=candidate.confidence,
                    source_file=notebook.visible_name if notebook else "",
                )
            )
            changed += 1
            continue

        if todo.removed_reason == REMOVED_BY_USER:
            continue  # deleted in the dashboard: extraction does not bring it back
        dirty = False
        if todo.removed_at is not None:
            todo.removed_at = None
            todo.removed_reason = None
            dirty = True
        if todo.text != candidate.text:
            todo.text = candidate.text
            todo.title = candidate.text[:200]
            todo.confidence = candidate.confidence
            dirty = True
        if candidate.completed and not todo.completed:
            todo.completed = True
            dirty = True
        if todo.page_number != page_number:
            todo.page_number = page_number
            dirty = True
        if dirty:
            todo.updated_at = now
            changed += 1

    for todo_id in todos_to_delete:
        todo = by_id[todo_id]
        if todo.removed_at is None:
            todo.removed_at = now
            todo.removed_reason = REMOVED_FROM_PAGE
            todo.updated_at = now
            changed += 1

    db.commit()
    if changed:
        logger.info(f"Todos of page {page.id}: {changed} created, changed or removed")

    _queue_todos_for_sync(db, user_id, page, notebook)
    return changed


def _queue_todos_for_sync(
    db: Session, user_id: int, page: Page, notebook: Optional[Notebook]
) -> None:
    """Queue the page's live todos for the user's enabled todo targets.

    Unchanged todos are not queued again (queue_sync checks sync_records per
    todo and target). Queueing errors are logged, not raised.
    """
    try:
        target_names = enabled_todo_targets(db, user_id)
        if not target_names:
            return
        todos = (
            db.query(Todo)
            .filter(
                Todo.page_id == page.id,
                Todo.user_id == user_id,
                Todo.removed_at.is_(None),
            )
            .all()
        )
        notebook_uuid = notebook.notebook_uuid if notebook else None
        queued = sum(
            len(queue_todo_sync(db, todo, notebook_uuid, target_names)) for todo in todos
        )
        if queued:
            logger.info(f"Queued {queued} todo sync item(s) for user {user_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error queuing todos for sync: {e}", exc_info=True)


def extract_todos_after_ocr(db: Session, page: Page, notebook: Notebook) -> None:
    """Todo step of ``on_ocr_completed``: extract, store and queue the page's todos.

    Runs for every page OCR'd with text, whether or not a todo target is
    connected (the todos table is the product's own record of tasks). Never
    raises: a failure is logged and rolled back so the caller's session stays
    usable and the upload succeeds.
    """
    try:
        process_page_todos(db, page, notebook.user_id, force_reprocess=True)
    except Exception as e:
        db.rollback()
        logger.error(f"Todo extraction failed for page {page.id}: {e}", exc_info=True)


def process_notebook_todos(
    db: Session, notebook_id: int, user_id: int, force_reprocess: bool = False
) -> int:
    """
    Extract and store todos from all pages in a notebook.

    Args:
        db: Database session
        notebook_id: Database ID of the notebook
        user_id: User ID for the todos
        force_reprocess: If True, reprocess even if todos already exist

    Returns:
        Total number of todos created/updated
    """
    notebook = db.query(Notebook).filter(Notebook.id == notebook_id).first()
    if not notebook:
        logger.error(f"Notebook {notebook_id} not found")
        return 0

    logger.info(
        f"Processing todos for notebook {notebook.visible_name} (ID: {notebook_id})"
    )

    # Every page OCR'd with text, the same pages on_ocr_completed extracts from
    # (a page need not have a notebook_pages row).
    pages = (
        db.query(Page)
        .filter(
            Page.notebook_id == notebook_id,
            Page.ocr_status == OcrStatus.COMPLETED.value,
            Page.ocr_text.isnot(None),
            Page.ocr_text != "",
        )
        .order_by(Page.id)
        .all()
    )

    logger.info(f"Found {len(pages)} pages with OCR text")

    total_todos = 0
    for page in pages:
        try:
            count = process_page_todos(db, page, user_id, force_reprocess)
            total_todos += count
        except Exception as e:
            db.rollback()
            logger.error(f"Error processing page {page.id}: {e}", exc_info=True)
            continue

    logger.info(
        f"Completed todo extraction for notebook {notebook.visible_name}: {total_todos} todos"
    )
    return total_todos
