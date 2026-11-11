"""Queued, coalesced notebook-metadata sync (title, path, page count, last opened).

The agent reports notebook metadata on every open on the tablet
(``POST /processing/metadata/update``). The endpoint only enqueues one
``notebook_metadata`` queue item per notebook and target; repeated opens
while it is pending reuse that item. The sync worker later builds the
metadata from the notebook row, updates the Notion page properties using the
notebook's sync record (``external_id``) and keeps a single ``sync_records``
row per (user, target, notebook_uuid).
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.sync_engine import ContentFingerprint, SyncItem, SyncResult
from app.models.notebook import Notebook
from app.models.sync_record import (
    IntegrationConfig,
    SyncItemType,
    SyncQueue,
    SyncRecord,
    SyncStatus,
)
from app.utils.concurrency import run_off_loop

logger = logging.getLogger(__name__)

ITEM_TYPE = SyncItemType.NOTEBOOK_METADATA.value  # "notebook_metadata"

# Targets that support metadata-only updates.
METADATA_SYNC_TARGETS = ("notion",)

# Behind fresh content (3) and normal items (5): metadata is cosmetic.
METADATA_SYNC_PRIORITY = 7


def build_notebook_metadata(notebook: Notebook) -> dict[str, Any]:
    """Lightweight metadata for a notebook (no page content)."""
    page_count = 0
    if notebook.content_json:
        try:
            content_data = json.loads(notebook.content_json)
            page_count = content_data.get("pageCount") or 0
            if not page_count:
                pages_array = content_data.get("pages") or []
                if not pages_array and "cPages" in content_data:
                    pages_array = content_data.get("cPages", {}).get("pages", [])
                page_count = len(pages_array)
        except (ValueError, TypeError, AttributeError) as e:
            logger.warning(f"Failed to parse content_json for page count: {e}")

    # reMarkable's own lastModified (ms since epoch) from metadata_json; not
    # notebook.updated_at, which changes on every database write.
    last_modified_at = None
    if notebook.metadata_json:
        try:
            meta = json.loads(notebook.metadata_json)
            if meta.get("lastModified"):
                last_modified_at = datetime.fromtimestamp(
                    int(meta["lastModified"]) / 1000.0
                ).isoformat()
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            logger.warning(f"Failed to parse lastModified from metadata_json: {e}")

    return {
        "notebook_uuid": notebook.notebook_uuid,
        "notebook_name": notebook.visible_name or "Untitled Notebook",
        "title": notebook.visible_name or "Untitled Notebook",
        "page_count": page_count,
        "full_path": notebook.full_path or "",
        "last_opened_at": notebook.last_opened.isoformat() if notebook.last_opened else None,
        "last_modified_at": last_modified_at,
    }


def queue_notebook_metadata_sync(db: Session, user_id: int, notebook: Notebook) -> list[SyncQueue]:
    """Enqueue a metadata sync for each enabled target, coalesced per notebook.

    If a pending item already exists for this notebook and target it is
    reused (the worker reads the notebook's current metadata when it runs),
    so repeated opens add no rows. Makes no external calls.

    Returns the pending queue items, new or reused.
    """
    integrations = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.user_id == user_id,
            IntegrationConfig.is_enabled == True,  # noqa: E712
            IntegrationConfig.target_name.in_(METADATA_SYNC_TARGETS),
        )
        .all()
    )
    if not integrations:
        return []

    content_hash = ContentFingerprint.for_notebook_metadata(build_notebook_metadata(notebook))
    now = datetime.utcnow()
    items = []
    for integration in integrations:
        item = (
            db.query(SyncQueue)
            .filter(
                SyncQueue.user_id == user_id,
                SyncQueue.target_name == integration.target_name,
                SyncQueue.item_type == ITEM_TYPE,
                SyncQueue.notebook_uuid == notebook.notebook_uuid,
                SyncQueue.status == "pending",
            )
            .first()
        )
        if item is not None:
            item.content_hash = content_hash
            item.updated_at = now
        else:
            item = SyncQueue(
                user_id=user_id,
                item_type=ITEM_TYPE,
                item_id=notebook.notebook_uuid,
                notebook_uuid=notebook.notebook_uuid,
                content_hash=content_hash,
                target_name=integration.target_name,
                status="pending",
                priority=METADATA_SYNC_PRIORITY,
                scheduled_at=now,
            )
            db.add(item)
        items.append(item)
    db.commit()
    return items


def _finish(queue_item: SyncQueue) -> None:
    queue_item.status = "completed"
    queue_item.completed_at = datetime.utcnow()
    queue_item.error_message = None


async def process_notebook_metadata_item(
    db: Session, queue_item: SyncQueue, config: IntegrationConfig
) -> None:
    """Sync one ``notebook_metadata`` queue item (called by the sync worker)."""
    from app.integrations.notion_sync import NotionSyncTarget
    from app.services.sync_worker import apply_sync_result

    notebook = (
        db.query(Notebook)
        .filter(
            Notebook.user_id == queue_item.user_id,
            Notebook.notebook_uuid == queue_item.notebook_uuid,
        )
        .first()
    )
    if notebook is None:
        queue_item.status = "failed"
        queue_item.error_message = "Notebook not found"
        db.commit()
        return

    if queue_item.target_name != "notion":
        queue_item.status = "failed"
        queue_item.error_message = f"Unknown target: {queue_item.target_name}"
        db.commit()
        return

    metadata = build_notebook_metadata(notebook)
    content_hash = ContentFingerprint.for_notebook_metadata(metadata)

    record: Optional[SyncRecord] = (
        db.query(SyncRecord)
        .filter(
            SyncRecord.user_id == queue_item.user_id,
            SyncRecord.target_name == queue_item.target_name,
            SyncRecord.item_type == ITEM_TYPE,
            SyncRecord.notebook_uuid == notebook.notebook_uuid,
        )
        .first()
    )
    if record is not None and record.status == "success" and record.content_hash == content_hash:
        _finish(queue_item)
        db.commit()
        return

    config_dict = config.get_config()
    target = NotionSyncTarget(
        access_token=config_dict.get("access_token"),
        database_id=config_dict.get("database_id"),
    )

    # The Notion page of the notebook, as recorded when it was first synced.
    notebook_record = (
        db.query(SyncRecord)
        .filter(
            SyncRecord.user_id == queue_item.user_id,
            SyncRecord.target_name == queue_item.target_name,
            SyncRecord.item_type == "notebook",
            SyncRecord.notebook_uuid == notebook.notebook_uuid,
        )
        .first()
    )

    if notebook_record is not None and notebook_record.external_id:
        updated = await run_off_loop(target._update_notion_page_properties)(
            notebook_record.external_id,
            notebook.notebook_uuid,
            metadata["title"],
            metadata["page_count"],
            metadata["full_path"],
            metadata["last_opened_at"],
            metadata["last_modified_at"],
        )
        result = (
            SyncResult(status=SyncStatus.SUCCESS, target_id=notebook_record.external_id)
            if updated
            else SyncResult(
                status=SyncStatus.RETRY, error_message="Failed to update Notion page metadata"
            )
        )
    else:
        # No notebook record (e.g. synced before records were kept): let the
        # target look the page up; it skips notebooks not in Notion yet.
        result = await target.sync_item(
            SyncItem(
                item_type=SyncItemType.NOTEBOOK_METADATA,
                item_id=notebook.notebook_uuid,
                content_hash=content_hash,
                data=metadata,
                source_table="notebooks",
                created_at=notebook.created_at,
                updated_at=notebook.updated_at,
            )
        )

    if not result.success:
        outcome = apply_sync_result(queue_item, result)
        logger.log(
            logging.INFO if outcome == "skipped" else logging.WARNING,
            "Notebook metadata sync %s: %s -> %s: %s",
            outcome,
            notebook.notebook_uuid,
            queue_item.target_name,
            result.error_message or (result.metadata or {}).get("reason"),
        )
        db.commit()
        return

    now = datetime.utcnow()
    if record is None:
        record = SyncRecord(
            user_id=queue_item.user_id,
            target_name=queue_item.target_name,
            item_type=ITEM_TYPE,
            item_id=notebook.notebook_uuid,
            notebook_uuid=notebook.notebook_uuid,
            created_at=now,
        )
        db.add(record)
    record.content_hash = content_hash
    record.external_id = result.target_id or ""
    record.status = "success"
    record.error_message = None
    record.synced_at = now
    record.updated_at = now
    _finish(queue_item)
    db.commit()
    logger.info(
        "Synced notebook metadata %s -> %s", notebook.notebook_uuid, queue_item.target_name
    )
