"""Pages deleted on the tablet: soft removal, undo, Notion cleanup and purge.

A notebook's page list (its ``.content`` file, or the page list the agent's
metadata sync sends) says which pages the notebook has. A page the list marks
deleted (``cPages.pages[].deleted.value``) or no longer lists is *removed*:

- ``pages.removed_at`` is set; the page loses its ``notebook_pages`` row
  (the caller rebuilds the order from the list) and is hidden wherever pages
  are shown or counted;
- its todos are marked removed (``REMOVED_FROM_PAGE``) so they stop syncing;
  their tasks in Todoist / Notion todos are left alone;
- with an enabled ``notion`` target, a ``page_removal`` queue row is added;
  the sync worker deletes the page's toggle block from the notebook's Notion
  page and forgets the page's sync record;
- the notebook's combined PDF is marked dirty (rebuilt by the worker).

A removed page that a later list names again is restored: ``removed_at`` is
cleared, a pending Notion removal is cancelled, and after the caller's commit
``finish_page_lists`` re-extracts its todos and queues its Notion sync (which
recreates the toggle in place).

Pages removed for longer than ``PAGE_PURGE_AFTER_DAYS`` are deleted for good by
``purge_removed_pages`` (called from the sync worker, about hourly).

``apply_page_lists`` is the one place that applies a page list; both the
``.content`` upload and the metadata sync call it, so they agree.
"""

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.integrations.registry import PAGE_REMOVAL
from app.models.notebook import Notebook
from app.models.page import Page
from app.models.sync_record import IntegrationConfig, SyncQueue, SyncRecord
from app.models.todo import REMOVED_FROM_PAGE, Todo
from app.utils.files import parse_uuid

logger = logging.getLogger(__name__)

# Days a removed page is kept (restorable by listing it again) before the
# sync worker deletes it, its files, todos and sync records for good.
PAGE_PURGE_AFTER_DAYS = 30
# How often one worker process runs the purge, and pages per run.
PAGE_PURGE_INTERVAL_SECONDS = 3600
PAGE_PURGE_BATCH = 50
# pg_try_advisory_lock class for the purge, so one worker purges at a time.
PAGE_PURGE_LOCK_CLASS = 0x50475247

# Only the notebook target holds page content; todo targets are left alone.
NOTION_TARGET = "notion"
# Ahead of fresh page syncs (3) and backfill (8).
PAGE_REMOVAL_PRIORITY = 4

# Rows per IN (...) list.
_IN_CHUNK = 1000


def _chunks(values: list, size: int = _IN_CHUNK):
    for i in range(0, len(values), size):
        yield values[i : i + size]


def parse_content_pages(content: Any) -> Optional[list[str]]:
    """Ordered page uuids a parsed ``.content`` file lists as present.

    Newer files keep deleted pages in ``cPages.pages`` with ``deleted.value``
    set; those are left out. ``cPages`` is preferred when it has entries; the
    plain ``pages`` list of older files has no deletion marks. Entries that are not UUIDs are skipped and duplicates keep their
    first position. Returns None when the file has no page list at all.
    """
    if not isinstance(content, dict):
        return None

    raw: list = []
    c_pages = content.get("cPages")
    entries = c_pages.get("pages") if isinstance(c_pages, dict) else None
    pages = content.get("pages")
    if isinstance(entries, list) and entries:
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                continue
            deleted = entry.get("deleted")
            if isinstance(deleted, dict) and deleted.get("value"):
                continue
            raw.append(entry["id"])
    elif isinstance(pages, list):
        raw = [p for p in pages if isinstance(p, str)]
    elif not isinstance(entries, list):
        return None

    listed: list[str] = []
    for value in raw:
        try:
            listed.append(parse_uuid(value))
        except ValueError:
            continue
    return list(dict.fromkeys(listed))


@dataclass
class PageListOutcome:
    """What ``apply_page_lists`` did, per notebook id."""

    # Notebooks whose list was not applied (empty, or it would remove every
    # live page); the caller leaves their page order as it is.
    skipped: set[int] = field(default_factory=set)
    removed: dict[int, list[int]] = field(default_factory=dict)  # notebook id -> page ids
    restored: dict[int, list[int]] = field(default_factory=dict)  # notebook id -> page ids

    @property
    def changed_notebooks(self) -> set[int]:
        return set(self.removed) | set(self.restored)


# (notebook id, page uuid) -> (page id, removed_at, has_content). has_content:
# the page's file was uploaded (not a stub registered from a page list).
PageIndex = dict[tuple[int, str], tuple[int, Optional[datetime], bool]]


def load_page_index(db: Session, user_id: int, notebook_ids: list[int]) -> PageIndex:
    """Pages (with a uuid) of the user's given notebooks, lowest id first."""
    index: PageIndex = {}
    for chunk in _chunks(sorted(set(notebook_ids))):
        rows = db.execute(
            select(Page.id, Page.notebook_id, Page.page_uuid, Page.removed_at, Page.s3_key)
            .join(Notebook, Notebook.id == Page.notebook_id)
            .where(
                Notebook.user_id == user_id,
                Page.notebook_id.in_(chunk),
                Page.page_uuid.isnot(None),
            )
            .order_by(Page.id)
        ).all()
        for page_id, nb_id, page_uuid, removed_at, s3_key in rows:
            index.setdefault((nb_id, page_uuid), (page_id, removed_at, bool(s3_key)))
    return index


def apply_page_lists(
    db: Session,
    user_id: int,
    page_lists: dict[int, list[str]],
    *,
    pages: Optional[PageIndex] = None,
    now: Optional[datetime] = None,
) -> PageListOutcome:
    """Remove and restore pages so each notebook matches its page list.

    ``page_lists`` maps a notebook id (owned by ``user_id``) to the ordered
    uuids of the pages it lists as present (deleted entries already left out).
    ``pages`` is the notebooks' existing pages (``load_page_index``); loaded
    here when not given. Only those pages are touched.

    Rules, per notebook:

    - an empty list removes nothing (skipped);
    - a live page the list does not name is removed;
    - a removed page the list names is restored;
    - if the list would remove every live page of a notebook that has one,
      or every live page whose file was uploaded (stubs registered from page
      lists do not count as kept), nothing is removed or restored and a
      warning is logged (skipped): a wrong or half-synced list must not wipe
      a notebook, however often it is sent.

    Writes to the session without committing. After the caller has rebuilt
    the page order and committed, it calls ``finish_page_lists``.
    """
    now = now or datetime.utcnow()
    if pages is None:
        pages = load_page_index(db, user_id, list(page_lists))

    by_notebook: dict[int, dict[str, tuple[int, Optional[datetime], bool]]] = {}
    for (nb_id, page_uuid), value in pages.items():
        if nb_id in page_lists and page_uuid:
            by_notebook.setdefault(nb_id, {})[page_uuid] = value

    outcome = PageListOutcome()
    for nb_id, listed in page_lists.items():
        if not listed:
            outcome.skipped.add(nb_id)
            continue
        listed_set = set(listed)
        nb_pages = by_notebook.get(nb_id, {})
        live = {u: pid for u, (pid, removed_at, _) in nb_pages.items() if removed_at is None}
        to_remove = sorted(pid for u, pid in live.items() if u not in listed_set)
        # Uploaded pages only: stubs registered from an earlier (refused) list
        # must not make a list look like it keeps some of the notebook.
        uploaded = {u for u, (_, removed_at, has_content) in nb_pages.items() if removed_at is None and has_content}
        if (uploaded and not uploaded & listed_set) or (live and len(to_remove) == len(live)):
            logger.warning(
                "Page list of notebook %s would remove all %d of its pages; ignoring it",
                nb_id,
                len(uploaded) or len(live),
                extra={"event": "pages.remove_all_refused", "notebook_id": nb_id},
            )
            outcome.skipped.add(nb_id)
            continue
        to_restore = sorted(
            pid
            for u, (pid, removed_at, _) in nb_pages.items()
            if removed_at is not None and u in listed_set
        )
        if to_remove:
            outcome.removed[nb_id] = to_remove
        if to_restore:
            outcome.restored[nb_id] = to_restore

    removed_ids = [pid for ids in outcome.removed.values() for pid in ids]
    restored_ids = [pid for ids in outcome.restored.values() for pid in ids]

    if removed_ids:
        _remove_pages(db, user_id, outcome.removed, now)
    if restored_ids:
        for chunk in _chunks(restored_ids):
            db.execute(
                update(Page).where(Page.id.in_(chunk)).values(removed_at=None),
                execution_options={"synchronize_session": False},
            )
            # A removal the worker has not run yet must not delete the toggle.
            db.execute(
                delete(SyncQueue).where(
                    SyncQueue.user_id == user_id,
                    SyncQueue.item_type == PAGE_REMOVAL,
                    SyncQueue.status == "pending",
                    SyncQueue.item_id.in_([str(pid) for pid in chunk]),
                ),
                execution_options={"synchronize_session": False},
            )
    changed = sorted(outcome.changed_notebooks)
    for chunk in _chunks(changed):
        # The combined notebook PDF no longer matches its pages.
        db.execute(
            update(Notebook).where(Notebook.id.in_(chunk)).values(pdf_dirty_at=now),
            execution_options={"synchronize_session": False},
        )

    if removed_ids or restored_ids:
        logger.info(
            "Page lists for user %s: %d page(s) removed, %d restored",
            user_id,
            len(removed_ids),
            len(restored_ids),
            extra={
                "event": "pages.page_list",
                "removed": len(removed_ids),
                "restored": len(restored_ids),
            },
        )
    return outcome


def _remove_pages(
    db: Session, user_id: int, removed: dict[int, list[int]], now: datetime
) -> None:
    page_ids = [pid for ids in removed.values() for pid in ids]
    for chunk in _chunks(page_ids):
        db.execute(
            update(Page)
            .where(Page.id.in_(chunk), Page.removed_at.is_(None))
            .values(removed_at=now),
            execution_options={"synchronize_session": False},
        )
        db.execute(
            update(Todo)
            .where(
                Todo.page_id.in_(chunk),
                Todo.user_id == user_id,
                Todo.removed_at.is_(None),
            )
            .values(removed_at=now, removed_reason=REMOVED_FROM_PAGE, updated_at=now),
            execution_options={"synchronize_session": False},
        )
    _queue_notion_removals(db, user_id, page_ids, now)


def removal_content_hash(page_uuid: str) -> str:
    return hashlib.sha256(f"page_removal:{page_uuid}".encode()).hexdigest()


def _queue_notion_removals(db: Session, user_id: int, page_ids: list[int], now: datetime) -> int:
    """Add a pending ``page_removal`` row per page for the user's enabled notion target."""
    enabled = db.execute(
        select(IntegrationConfig.id).where(
            IntegrationConfig.user_id == user_id,
            IntegrationConfig.target_name == NOTION_TARGET,
            IntegrationConfig.is_enabled == True,  # noqa: E712
        )
    ).first()
    if enabled is None:
        return 0

    rows = []
    for chunk in _chunks(page_ids):
        already = {
            item_id
            for (item_id,) in db.execute(
                select(SyncQueue.item_id).where(
                    SyncQueue.user_id == user_id,
                    SyncQueue.target_name == NOTION_TARGET,
                    SyncQueue.item_type == PAGE_REMOVAL,
                    SyncQueue.status == "pending",
                    SyncQueue.item_id.in_([str(pid) for pid in chunk]),
                )
            )
        }
        page_rows = db.execute(
            select(Page.id, Page.page_uuid, Notebook.notebook_uuid)
            .join(Notebook, Notebook.id == Page.notebook_id)
            .where(Page.id.in_(chunk))
        ).all()
        for page_id, page_uuid, notebook_uuid in page_rows:
            if str(page_id) in already or not page_uuid:
                continue
            rows.append(
                SyncQueue(
                    user_id=user_id,
                    item_type=PAGE_REMOVAL,
                    item_id=str(page_id),
                    content_hash=removal_content_hash(page_uuid),
                    page_uuid=page_uuid,
                    notebook_uuid=notebook_uuid,
                    target_name=NOTION_TARGET,
                    status="pending",
                    priority=PAGE_REMOVAL_PRIORITY,
                    scheduled_at=now,
                )
            )
    db.add_all(rows)
    return len(rows)


def finish_page_lists(db: Session, user_id: int, outcome: PageListOutcome) -> None:
    """Follow-up work after ``apply_page_lists`` and the caller's commit.

    Restored pages get their todos re-extracted (which un-removes the matched
    todos) and their text queued for the notebook targets; every changed
    notebook gets its Obsidian content hash recomputed. Commits; failures are
    logged per page and never raised. Makes no external calls.
    """
    if not outcome.changed_notebooks:
        return
    # Imported here: page_events imports the todo extractor and sync queue.
    from app.processors.todo_extractor import process_page_todos
    from app.services.page_events import enqueue_integration_syncs, update_obsidian_content_hash

    for nb_id, page_ids in outcome.restored.items():
        for page_id in page_ids:
            try:
                page = db.get(Page, page_id)
                if page is None or page.removed_at is not None:
                    continue
                notebook = db.get(Notebook, page.notebook_id)
                if notebook is None or notebook.user_id != user_id:
                    continue
                process_page_todos(db, page, user_id, force_reprocess=True)
                if page.ocr_status == "completed" and page.ocr_text:
                    enqueue_integration_syncs(db, page, notebook)
            except Exception:
                db.rollback()
                logger.error("Follow-up for restored page %s failed", page_id, exc_info=True)

    for nb_id in sorted(outcome.changed_notebooks):
        notebook = db.get(Notebook, nb_id)
        if notebook is not None:
            update_obsidian_content_hash(db, notebook)


# ---------------------------------------------------------------------------
# Purge
# ---------------------------------------------------------------------------


async def _delete_stored_file(storage, key: str) -> bool:
    """Delete one stored file; True when it is gone afterwards."""
    if await storage.delete_file(key):
        return True
    # False means "did not exist" (local) or a client error (S3): look again.
    return not await storage.file_exists(key)


async def purge_removed_pages(
    db: Session,
    storage,
    *,
    now: Optional[datetime] = None,
    older_than: timedelta = timedelta(days=PAGE_PURGE_AFTER_DAYS),
    limit: int = PAGE_PURGE_BATCH,
) -> int:
    """Delete pages removed longer than ``older_than`` ago, at most ``limit`` per call.

    For each page: the row is locked and re-checked, then its stored files
    (``.rm`` and PDF) are deleted; if one cannot be deleted the page is left
    for the next run. Then its todos,
    todos' sync records and queue rows, the page's sync records and queue
    rows, and the page row itself (``notebook_pages`` rows cascade) are
    deleted and committed together. Remote tasks and blocks are not touched. A page
    restored meanwhile is not deleted (the delete re-checks ``removed_at``).

    Returns the number of pages deleted.
    """
    now = now or datetime.utcnow()
    cutoff = now - older_than
    candidates = db.execute(
        select(
            Page.id,
            Page.page_uuid,
            Page.s3_key,
            Page.pdf_s3_key,
            Notebook.user_id,
            Notebook.notebook_uuid,
        )
        .join(Notebook, Notebook.id == Page.notebook_id)
        .where(Page.removed_at.isnot(None), Page.removed_at < cutoff)
        .order_by(Page.removed_at, Page.id)
        .limit(limit)
    ).all()

    purged = 0
    for page_id, page_uuid, s3_key, pdf_key, user_id, notebook_uuid in candidates:
        try:
            # Lock the row first (PostgreSQL; SQLite has one writer anyway) and
            # keep the lock until the page row is deleted: a restore of this
            # page waits, then finds no page, instead of reviving a page whose
            # files were just deleted. Not removed any more: leave it alone.
            still_removed = db.execute(
                select(Page.id)
                .where(
                    Page.id == page_id,
                    Page.removed_at.isnot(None),
                    Page.removed_at < cutoff,
                )
                .with_for_update()
            ).first()
            if still_removed is None:
                db.rollback()
                continue

            keys = [key for key in (s3_key, pdf_key) if key]
            gone = True
            for key in keys:
                try:
                    if not await _delete_stored_file(storage, key):
                        gone = False
                except Exception:
                    logger.warning("Could not delete stored file of removed page %s", page_id, exc_info=True)
                    gone = False
            if not gone:
                db.rollback()  # release the row lock
                continue  # retried on the next run

            todo_ids = [
                str(todo_id)
                for (todo_id,) in db.execute(
                    select(Todo.id).where(Todo.page_id == page_id, Todo.user_id == user_id)
                )
            ]
            for chunk in _chunks(todo_ids):
                db.execute(
                    delete(SyncRecord).where(
                        SyncRecord.user_id == user_id,
                        SyncRecord.item_type == "todo",
                        SyncRecord.item_id.in_(chunk),
                    ),
                    execution_options={"synchronize_session": False},
                )
                db.execute(
                    delete(SyncQueue).where(
                        SyncQueue.user_id == user_id,
                        SyncQueue.item_type == "todo",
                        SyncQueue.item_id.in_(chunk),
                    ),
                    execution_options={"synchronize_session": False},
                )
            # Todos first: todos.page_id is ON DELETE SET NULL.
            db.execute(
                delete(Todo).where(Todo.page_id == page_id, Todo.user_id == user_id),
                execution_options={"synchronize_session": False},
            )
            db.execute(
                delete(SyncQueue).where(
                    SyncQueue.user_id == user_id,
                    SyncQueue.item_id == str(page_id),
                    SyncQueue.item_type.in_(("page_text", PAGE_REMOVAL)),
                ),
                execution_options={"synchronize_session": False},
            )
            if page_uuid:
                db.execute(
                    delete(SyncRecord).where(
                        SyncRecord.user_id == user_id,
                        SyncRecord.page_uuid == page_uuid,
                        SyncRecord.notebook_uuid == notebook_uuid,
                    ),
                    execution_options={"synchronize_session": False},
                )
            # notebook_pages rows cascade. Re-checked: a page restored since the
            # query above is not deleted (and the writes above are rolled back).
            deleted = db.execute(
                delete(Page).where(
                    Page.id == page_id,
                    Page.removed_at.isnot(None),
                    Page.removed_at < cutoff,
                ),
                execution_options={"synchronize_session": False},
            ).rowcount
            if not deleted:
                db.rollback()
                continue
            db.commit()
            purged += 1
        except Exception:
            db.rollback()
            logger.error("Purging removed page %s failed", page_id, exc_info=True)
    if purged:
        logger.info(
            "Purged %d page(s) removed more than %s ago",
            purged,
            older_than,
            extra={"event": "pages.purged", "purged": purged},
        )
    return purged
