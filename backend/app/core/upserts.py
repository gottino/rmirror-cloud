"""Race-free find-or-create for notebooks and pages.

A query followed by an insert lets two concurrent requests for the same
reMarkable document both miss and both insert. These helpers insert with
``ON CONFLICT DO NOTHING`` against the unique indexes
``uq_notebooks_user_notebook_uuid`` and ``uq_pages_notebook_page_uuid`` and
then load the row, so concurrent callers end up with the same single row.
The caller applies any updates to the returned object and commits as before.
"""

from typing import Any

from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from app.models.notebook import Notebook
from app.models.page import Page


def dialect_insert(db: Session, model):
    """An ``INSERT`` for the session's dialect that supports ``ON CONFLICT``."""
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        return postgresql.insert(model.__table__)
    if dialect == "sqlite":
        return sqlite.insert(model.__table__)
    # pragma: no cover - only PostgreSQL and SQLite are supported
    raise NotImplementedError(f"Unsupported database dialect: {dialect}")


def insert_ignoring_conflicts(db: Session, model, keys: list[str] | None = None):
    """``INSERT ... ON CONFLICT (keys) DO NOTHING`` for the session's dialect.

    With ``keys=None`` any unique violation is ignored. Works with a single
    ``.values(...)`` and with a list of parameter sets (``RETURNING`` then
    yields only the rows actually inserted).
    """
    return dialect_insert(db, model).on_conflict_do_nothing(index_elements=keys)


def _insert_ignore_conflict(db: Session, model, values: dict[str, Any], keys: list[str]) -> bool:
    """INSERT ... ON CONFLICT (keys) DO NOTHING. Returns True if a row was inserted."""
    result = db.execute(insert_ignoring_conflicts(db, model, keys).values(**values))
    return result.rowcount == 1


def get_or_create_notebook(
    db: Session, user_id: int, notebook_uuid: str, **create_values: Any
) -> tuple[Notebook, bool]:
    """Return the user's notebook with this uuid, inserting it if missing.

    ``create_values`` are used only when the row is inserted; they must include
    the non-nullable columns (``visible_name``, ``document_type``).
    Returns ``(notebook, created)``.
    """
    values = {**create_values, "user_id": user_id, "notebook_uuid": notebook_uuid}
    created = _insert_ignore_conflict(db, Notebook, values, ["user_id", "notebook_uuid"])
    notebook = (
        db.query(Notebook)
        .filter(Notebook.user_id == user_id, Notebook.notebook_uuid == notebook_uuid)
        .one()
    )
    return notebook, created


def get_or_create_page(
    db: Session, notebook_id: int, page_uuid: str, **create_values: Any
) -> tuple[Page, bool]:
    """Return the notebook's page with this uuid, inserting it if missing.

    ``create_values`` are used only when the row is inserted.
    Returns ``(page, created)``.
    """
    values = {**create_values, "notebook_id": notebook_id, "page_uuid": page_uuid}
    created = _insert_ignore_conflict(db, Page, values, ["notebook_id", "page_uuid"])
    page = (
        db.query(Page)
        .filter(Page.notebook_id == notebook_id, Page.page_uuid == page_uuid)
        .one()
    )
    return page, created
