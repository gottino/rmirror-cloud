"""API endpoints for todo management."""

import logging
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.clerk import get_clerk_active_user, reject_agent_token
from app.database import SessionLocal, get_db
from app.models.notebook import Notebook
from app.models.todo import REMOVED_BY_USER, Todo
from app.models.user import User
from app.processors.todo_extractor import process_notebook_todos
from app.services.sync_queue import queue_stored_todos, queue_todo_sync

logger = logging.getLogger(__name__)
# Todos are dashboard-only; the Mac agent never calls them, so block agent tokens.
router = APIRouter(tags=["todos"], dependencies=[Depends(reject_agent_token)])


# Schemas
class TodoSchema(BaseModel):
    """Todo item response schema."""

    id: int
    notebook_id: int
    page_id: Optional[int]
    page_number: Optional[int]
    page_uuid: Optional[str]
    title: str
    text: str
    completed: bool
    confidence: Optional[float]
    source_file: Optional[str]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class TodoUpdateRequest(BaseModel):
    """Request to update a todo."""

    completed: Optional[bool] = None
    text: Optional[str] = None


class TodoExtractionRequest(BaseModel):
    """Request to extract todos from notebooks."""

    notebook_ids: Optional[list[int]] = None  # Specific notebooks, or None for all
    force_reprocess: bool = False


class TodoExtractionResponse(BaseModel):
    """Response from todo extraction."""

    success: bool
    message: str
    notebooks_processed: int
    todos_extracted: int


class TodoStatsResponse(BaseModel):
    """Todo statistics."""

    total_todos: int
    completed_todos: int
    pending_todos: int
    notebooks_with_todos: int


# Endpoints
@router.get("/", response_model=list[TodoSchema])
async def list_todos(
    current_user: Annotated[User, Depends(get_clerk_active_user)],
    db: Annotated[Session, Depends(get_db)],
    notebook_id: Optional[int] = Query(None, description="Filter by notebook ID"),
    completed: Optional[bool] = Query(None, description="Filter by completion status"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of todos"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """
    List todos for the current user.

    Supports filtering by notebook and completion status.
    """
    query = db.query(Todo).filter(Todo.user_id == current_user.id, Todo.removed_at.is_(None))

    if notebook_id is not None:
        query = query.filter(Todo.notebook_id == notebook_id)

    if completed is not None:
        query = query.filter(Todo.completed == completed)

    # Order by notebook, page number, creation date
    query = query.order_by(
        Todo.notebook_id, Todo.page_number, Todo.created_at.desc()
    )

    todos = query.offset(offset).limit(limit).all()

    return [
        TodoSchema(
            id=todo.id,
            notebook_id=todo.notebook_id,
            page_id=todo.page_id,
            page_number=todo.page_number,
            page_uuid=todo.page_uuid,
            title=todo.title,
            text=todo.text,
            completed=todo.completed,
            confidence=todo.confidence,
            source_file=todo.source_file,
            created_at=todo.created_at.isoformat(),
            updated_at=todo.updated_at.isoformat(),
        )
        for todo in todos
    ]


@router.get("/{todo_id}", response_model=TodoSchema)
async def get_todo(
    todo_id: int,
    current_user: Annotated[User, Depends(get_clerk_active_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Get a specific todo by ID."""
    todo = (
        db.query(Todo)
        .filter(
            Todo.id == todo_id, Todo.user_id == current_user.id, Todo.removed_at.is_(None)
        )
        .first()
    )

    if not todo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found"
        )

    return TodoSchema(
        id=todo.id,
        notebook_id=todo.notebook_id,
        page_id=todo.page_id,
        page_number=todo.page_number,
        page_uuid=todo.page_uuid,
        title=todo.title,
        text=todo.text,
        completed=todo.completed,
        confidence=todo.confidence,
        source_file=todo.source_file,
        created_at=todo.created_at.isoformat(),
        updated_at=todo.updated_at.isoformat(),
    )


@router.patch("/{todo_id}", response_model=TodoSchema)
async def update_todo(
    todo_id: int,
    request: TodoUpdateRequest,
    current_user: Annotated[User, Depends(get_clerk_active_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Update a todo (e.g., mark as completed)."""
    todo = (
        db.query(Todo)
        .filter(
            Todo.id == todo_id, Todo.user_id == current_user.id, Todo.removed_at.is_(None)
        )
        .first()
    )

    if not todo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found"
        )

    # Update fields
    if request.completed is not None:
        todo.completed = request.completed

    if request.text is not None:
        todo.text = request.text
        todo.title = request.text[:200]

    db.commit()
    db.refresh(todo)

    # Send the change to the user's todo targets (queued; the worker syncs it).
    notebook = db.query(Notebook).filter(Notebook.id == todo.notebook_id).first()
    queue_todo_sync(db, todo, notebook.notebook_uuid if notebook else None)

    return TodoSchema(
        id=todo.id,
        notebook_id=todo.notebook_id,
        page_id=todo.page_id,
        page_number=todo.page_number,
        page_uuid=todo.page_uuid,
        title=todo.title,
        text=todo.text,
        completed=todo.completed,
        confidence=todo.confidence,
        source_file=todo.source_file,
        created_at=todo.created_at.isoformat(),
        updated_at=todo.updated_at.isoformat(),
    )


@router.delete("/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_todo(
    todo_id: int,
    current_user: Annotated[User, Depends(get_clerk_active_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Delete a todo.

    The todo is marked removed (it disappears from the list and is not
    extracted again from its page). Its task in Todoist or Notion is left as
    it is: nothing is deleted there.
    """
    todo = (
        db.query(Todo)
        .filter(
            Todo.id == todo_id, Todo.user_id == current_user.id, Todo.removed_at.is_(None)
        )
        .first()
    )

    if not todo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found"
        )

    todo.removed_at = datetime.utcnow()
    todo.removed_reason = REMOVED_BY_USER
    db.commit()


@router.post("/extract", response_model=TodoExtractionResponse)
async def extract_todos(
    request: TodoExtractionRequest,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_clerk_active_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """
    Extract todos from notebooks (backfill).

    Todos are extracted automatically after every OCR; this re-runs the same
    extraction for pages OCR'd before that, and then queues every stored todo
    that a connected todo target does not have yet (once per target). Runs in
    the background.
    """
    # Get notebooks to process
    if request.notebook_ids:
        notebooks = (
            db.query(Notebook)
            .filter(
                Notebook.user_id == current_user.id, Notebook.id.in_(request.notebook_ids)
            )
            .all()
        )
    else:
        # Process all user's notebooks
        notebooks = db.query(Notebook).filter(Notebook.user_id == current_user.id).all()

    if not notebooks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No notebooks found"
        )

    # Start extraction in background
    notebook_ids = [nb.id for nb in notebooks]
    background_tasks.add_task(
        _run_todo_extraction, notebook_ids, current_user.id, request.force_reprocess
    )

    return TodoExtractionResponse(
        success=True,
        message=f"Todo extraction started for {len(notebooks)} notebook(s)",
        notebooks_processed=0,  # Will be updated in background
        todos_extracted=0,  # Will be updated in background
    )


def _run_todo_extraction(notebook_ids: list[int], user_id: int, force_reprocess: bool):
    """Run todo extraction in the background (in a worker thread, own session)."""
    db = SessionLocal()
    try:
        total_todos = 0
        for notebook_id in notebook_ids:
            try:
                count = process_notebook_todos(db, notebook_id, user_id, force_reprocess)
                total_todos += count
            except Exception as e:
                db.rollback()
                logger.error(
                    f"Error extracting todos from notebook {notebook_id}: {e}",
                    exc_info=True,
                )
                continue

        queued = queue_stored_todos(db, user_id)
        logger.info(
            f"Todo extraction completed: {len(notebook_ids)} notebooks, "
            f"{total_todos} todos, {queued} queued for todo targets"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error in background todo extraction: {e}", exc_info=True)
    finally:
        db.close()


@router.get("/stats/summary", response_model=TodoStatsResponse)
async def get_todo_stats(
    current_user: Annotated[User, Depends(get_clerk_active_user)],
    db: Annotated[Session, Depends(get_db)],
):
    """Get todo statistics for the current user."""
    live = (Todo.user_id == current_user.id, Todo.removed_at.is_(None))
    total_todos = db.query(Todo).filter(*live).count()

    completed_todos = (
        db.query(Todo)
        .filter(*live, Todo.completed == True)  # noqa: E712
        .count()
    )

    pending_todos = total_todos - completed_todos

    notebooks_with_todos = (
        db.query(func.count(func.distinct(Todo.notebook_id)))
        .filter(*live)
        .scalar()
    )

    return TodoStatsResponse(
        total_todos=total_todos,
        completed_todos=completed_todos,
        pending_todos=pending_todos,
        notebooks_with_todos=notebooks_with_todos or 0,
    )
