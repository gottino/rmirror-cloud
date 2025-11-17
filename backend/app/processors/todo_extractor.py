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
from app.models.page import Page
from app.models.todo import Todo
from app.processors.intelligent_todo_deduplication import (
    IntelligentTodoDeduplicator,
    TodoCandidate,
    create_todo_candidate,
)

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
    Extract and store todos from a single page.

    Args:
        db: Database session
        page: Page object to process
        user_id: User ID for the todos
        force_reprocess: If True, reprocess even if todos already exist

    Returns:
        Number of todos created/updated
    """
    if not page.ocr_text or not page.ocr_text.strip():
        logger.debug(f"Page {page.id} has no OCR text, skipping todo extraction")
        return 0

    # Check if we should skip this page
    if not force_reprocess:
        existing_count = (
            db.query(Todo)
            .filter(Todo.page_id == page.id, Todo.user_id == user_id)
            .count()
        )
        if existing_count > 0:
            logger.debug(
                f"Page {page.id} already has {existing_count} todos, skipping"
            )
            return 0

    # Extract todos from OCR text
    new_todos = extract_todos_from_text(
        text=page.ocr_text,
        notebook_id=page.notebook_id,
        page_number=page.page_number,
        page_id=page.id,
    )

    if not new_todos:
        logger.debug(f"No todos found in page {page.id}")
        return 0

    logger.info(f"Extracted {len(new_todos)} todos from page {page.id}")

    # Get existing todos for this page
    existing_todos = (
        db.query(Todo)
        .filter(Todo.page_id == page.id, Todo.user_id == user_id)
        .all()
    )

    existing_todos_dict = [
        {
            "id": todo.id,
            "text": todo.text,
            "confidence": todo.confidence or 1.0,
            "page_number": todo.page_number,
            "completed": todo.completed,
            "bounding_box": todo.bounding_box,
        }
        for todo in existing_todos
    ]

    # Deduplicate
    deduplicator = IntelligentTodoDeduplicator(
        similarity_threshold=0.8,
        position_threshold=50.0,
        confidence_improvement_threshold=0.1,
    )

    final_todos, todos_to_delete = deduplicator.deduplicate_todos_for_page(
        new_todos, existing_todos_dict
    )

    # Store todos
    stored_count = 0
    for candidate in final_todos:
        if candidate.existing_id:
            # Update existing todo
            existing_todo = db.query(Todo).filter(Todo.id == candidate.existing_id).first()
            if existing_todo:
                existing_todo.text = candidate.text
                existing_todo.title = candidate.text[:200]
                existing_todo.confidence = candidate.confidence
                existing_todo.completed = candidate.completed
                existing_todo.updated_at = datetime.utcnow()
                stored_count += 1
                logger.debug(f"Updated todo {existing_todo.id}")
        else:
            # Insert new todo
            new_todo = Todo(
                user_id=user_id,
                notebook_id=candidate.notebook_id,
                page_id=candidate.page_id,
                page_number=candidate.page_number,
                page_uuid=page.page_uuid if page.page_uuid else None,
                title=candidate.text[:200],
                text=candidate.text,
                completed=candidate.completed,
                confidence=candidate.confidence,
                source_file=page.notebook.visible_name if page.notebook else "",
            )
            db.add(new_todo)
            stored_count += 1
            logger.debug(f"Created new todo: {new_todo.text[:50]}...")

    # Commit changes
    db.commit()
    logger.info(f"Stored {stored_count} todos for page {page.id}")
    return stored_count


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

    # Get all pages with OCR text
    pages = (
        db.query(Page)
        .filter(
            Page.notebook_id == notebook_id,
            Page.ocr_text.isnot(None),
            Page.ocr_text != "",
        )
        .order_by(Page.page_number)
        .all()
    )

    logger.info(f"Found {len(pages)} pages with OCR text")

    total_todos = 0
    for page in pages:
        try:
            count = process_page_todos(db, page, user_id, force_reprocess)
            total_todos += count
        except Exception as e:
            logger.error(f"Error processing page {page.id}: {e}", exc_info=True)
            continue

    logger.info(
        f"Completed todo extraction for notebook {notebook.visible_name}: {total_todos} todos"
    )
    return total_todos
