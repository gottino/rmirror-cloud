"""Notion sync target implementation for rmirror Cloud."""

import logging
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional

import httpx
from notion_client import Client as NotionClient
from notion_client.errors import HTTPResponseError, RequestTimeoutError

from app.core.sync_engine import (
    RATE_LIMIT_DEFAULT_DELAY,
    SyncErrorKind,
    SyncItem,
    SyncResult,
    SyncTarget,
)
from app.integrations.notion_markdown import MarkdownToNotionConverter
from app.models.sync_record import SyncItemType, SyncStatus
from app.utils.concurrency import run_off_loop

logger = logging.getLogger(__name__)

# Never wait longer than this on a provider's Retry-After.
_MAX_RETRY_AFTER = timedelta(hours=1)

# Page toggles are titled "📄 Page N". A second, gray rich_text segment
# " · <first 8 chars of the reMarkable page uuid>" marks which page a toggle
# belongs to, so a retry after a crash can find a toggle it already appended.
_PAGE_TITLE_RE = re.compile(r"📄 Page (\d+)")
_MARKER_PREFIX = " · "


class NotionSyncError(Exception):
    """A Notion failure already classified into a SyncErrorKind."""

    def __init__(
        self, kind: SyncErrorKind, message: str, retry_after: Optional[datetime] = None
    ):
        super().__init__(message)
        self.kind = kind
        self.retry_after = retry_after


def _retry_after_from_headers(headers: Any) -> datetime:
    """Naive-UTC time to retry at, from a Retry-After header (seconds or HTTP date)."""
    now = datetime.utcnow()
    value = None
    try:
        value = headers.get("Retry-After") if headers is not None else None
    except Exception:
        value = None
    delay = RATE_LIMIT_DEFAULT_DELAY
    if isinstance(value, str) and value.strip():
        try:
            delay = timedelta(seconds=max(float(value), 0.0))
        except ValueError:
            try:
                when = parsedate_to_datetime(value)
                if when.tzinfo is not None:
                    when = when.astimezone(timezone.utc).replace(tzinfo=None)
                delay = max(when - now, timedelta(0))
            except (TypeError, ValueError):
                pass
    return now + min(delay, _MAX_RETRY_AFTER)


def _error_code(exc: BaseException) -> Optional[str]:
    code = getattr(exc, "code", None)
    return getattr(code, "value", code) if code is not None else None


def _classify_status(
    status: int, code: Optional[str], headers: Any, message: str
) -> NotionSyncError:
    """Map a Notion HTTP status / API error code to a typed error."""
    if code == "rate_limited" or status == 429:
        return NotionSyncError(
            SyncErrorKind.RATE_LIMITED, message, _retry_after_from_headers(headers)
        )
    if code in ("unauthorized", "restricted_resource") or status in (401, 403):
        return NotionSyncError(SyncErrorKind.AUTH, message)
    if (
        code in ("internal_server_error", "service_unavailable", "conflict_error")
        or status >= 500
        or status in (408, 409)
    ):
        return NotionSyncError(SyncErrorKind.TRANSIENT, message)
    if 400 <= status < 500:
        return NotionSyncError(SyncErrorKind.PERMANENT, message)
    return NotionSyncError(SyncErrorKind.TRANSIENT, message)


def classify_notion_error(exc: BaseException) -> Optional[NotionSyncError]:
    """Classify an exception from the Notion SDK or httpx; None if unrecognised."""
    if isinstance(exc, NotionSyncError):
        return exc
    if isinstance(exc, HTTPResponseError):
        return _classify_status(exc.status, _error_code(exc), exc.headers, str(exc))
    if isinstance(exc, (RequestTimeoutError, httpx.TransportError)):
        return NotionSyncError(SyncErrorKind.TRANSIENT, str(exc) or type(exc).__name__)
    return None


def _is_gone(exc: BaseException) -> bool:
    """True if Notion says the object is missing or archived."""
    if isinstance(exc, HTTPResponseError):
        if _error_code(exc) == "object_not_found" or exc.status == 404:
            return True
        return exc.status == 400 and "archived" in str(exc).lower()
    if isinstance(exc, NotionSyncError):
        return False
    # Untyped errors: keep the historic message heuristics.
    message = str(exc).lower()
    return "archived" in message or "not found" in message or "could not find" in message


def _norm_id(block_id: Optional[str]) -> str:
    return (block_id or "").replace("-", "").lower()


def _toggle_segments(block: Dict) -> List[Dict]:
    return block.get("toggle", {}).get("rich_text", []) or []


def _segment_text(segment: Dict) -> str:
    return segment.get("text", {}).get("content") or segment.get("plain_text") or ""


def _toggle_marker(block: Dict) -> Optional[str]:
    """The page marker of a toggle we built, or None for unmarked/foreign toggles."""
    for segment in _toggle_segments(block)[1:]:
        text = _segment_text(segment)
        if text.startswith(_MARKER_PREFIX):
            return text[len(_MARKER_PREFIX):].strip()
    return None


def _page_marker(page_uuid: str) -> str:
    return page_uuid[:8]


class NotionSyncTarget(SyncTarget):
    """
    Notion implementation of the sync target interface.

    This handles syncing notebooks and pages to a Notion database.
    """

    def __init__(self, access_token: str, database_id: str, verify_ssl: bool = True):
        """
        Initialize Notion sync target.

        Args:
            access_token: Notion OAuth access token or integration API token
            database_id: Notion database ID for notebooks
            verify_ssl: Whether to verify SSL certificates (default: True)
        """
        super().__init__("notion")
        self.access_token = access_token
        self.database_id = database_id
        self.verify_ssl = verify_ssl

        # Create httpx client with SSL verification control
        if not verify_ssl:
            self.logger.warning("⚠️ SSL verification disabled for Notion API calls")
            http_client = httpx.Client(verify=False)
            self.client = NotionClient(
                auth=access_token,
                client=http_client,
                notion_version="2025-09-03"
            )
        else:
            self.client = NotionClient(
                auth=access_token,
                notion_version="2025-09-03"
            )

        self.markdown_converter = MarkdownToNotionConverter()
        self.logger.info(f"Initialized Notion sync target with database {database_id}")

    @run_off_loop
    async def sync_item(self, item: SyncItem) -> SyncResult:
        """Sync a single item to Notion."""
        try:
            if item.item_type == SyncItemType.NOTEBOOK_METADATA:
                return await self._sync_notebook_metadata(item)
            elif item.item_type == SyncItemType.PAGE_TEXT:
                return await self._sync_page_text(item)
            elif item.item_type == SyncItemType.TODO:
                return SyncResult(
                    status=SyncStatus.SKIPPED,
                    metadata={"reason": "Todos should use notion-todos integration"},
                )
            elif item.item_type == SyncItemType.HIGHLIGHT:
                return SyncResult(
                    status=SyncStatus.SKIPPED,
                    metadata={"reason": "Highlights handled via notebook sync"},
                )
            else:
                return SyncResult(
                    status=SyncStatus.FAILED,
                    error_message=f"Unsupported item type: {item.item_type}",
                )
        except Exception as e:
            self.logger.error(f"Error syncing {item.item_type} to Notion: {e}")
            return SyncResult(status=SyncStatus.FAILED, error_message=str(e))

    async def _sync_notebook_metadata(self, item: SyncItem) -> SyncResult:
        """
        Sync only notebook metadata (lightweight operation).

        This updates the Notion page properties without touching page content blocks.
        Used when only metadata changes (e.g., lastOpened timestamp).
        """
        try:
            notebook_data = item.data
            notebook_uuid = notebook_data.get("notebook_uuid")
            title = notebook_data.get("title", "Untitled Notebook")
            full_path = notebook_data.get("full_path", "")
            page_count = notebook_data.get("page_count", 0)
            last_opened = notebook_data.get("last_opened_at")
            last_modified = notebook_data.get("last_modified_at")

            # Check if page exists
            existing_page_id = await self.find_existing_page(notebook_uuid)

            if not existing_page_id:
                # Page doesn't exist yet - skip metadata-only sync
                return SyncResult(
                    status=SyncStatus.SKIPPED,
                    metadata={"reason": "Notebook not yet synced, use full notebook sync first"},
                )

            # Update only the properties (metadata), not the content blocks
            success = await self._update_notion_page_properties(
                existing_page_id, notebook_uuid, title, page_count, full_path,
                last_opened, last_modified
            )

            if success:
                return SyncResult(
                    status=SyncStatus.SUCCESS,
                    target_id=existing_page_id,
                    metadata={"action": "metadata_updated"},
                )
            else:
                return SyncResult(
                    status=SyncStatus.RETRY,
                    error_message="Failed to update Notion page metadata",
                )

        except Exception as e:
            self.logger.error(f"Error syncing notebook metadata to Notion: {e}")
            return self._error_result(e)

    @staticmethod
    def _error_result(exc: BaseException) -> SyncResult:
        """SyncResult for a failed attempt, typed when the error is recognised."""
        err = classify_notion_error(exc)
        if err is None:
            # Unrecognised: no kind, so the worker falls back to its message rules.
            return SyncResult(status=SyncStatus.FAILED, error_message=str(exc))
        retryable = err.kind in (
            SyncErrorKind.RATE_LIMITED,
            SyncErrorKind.TRANSIENT,
            SyncErrorKind.PARENT_GONE,
        )
        return SyncResult(
            status=SyncStatus.RETRY if retryable else SyncStatus.FAILED,
            error_message=str(err),
            retry_after=err.retry_after,
            error_kind=err.kind,
        )

    async def _sync_page_text(self, item: SyncItem) -> SyncResult:
        """
        Sync individual page text to Notion using database-tracked block IDs.

        The worker passes ``existing_block_id`` (the page's SyncRecord),
        ``existing_notebook_page_id`` (the notebook's SyncRecord),
        ``stale_block_ids`` (old blocks an earlier update could not delete) and
        ``claimed_block_ids`` (blocks other pages' SyncRecords point at).

        Writes are ordered so a failure at any step can be retried safely:
        the new toggle is appended first, and the block it replaces is deleted
        only after that succeeded. If that delete fails, the sync still counts
        and the old id is returned in ``metadata["stale_block_ids"]`` for the
        next sync of this page to remove. A toggle already appended by an
        attempt whose result was never recorded is found by its page marker
        and replaced rather than duplicated.

        Failures come back typed (``SyncResult.error_kind``); PARENT_GONE means
        the notebook's Notion page is archived or missing.
        """
        try:
            page_data = item.data
            page_text = page_data.get("text", "")
            page_number = page_data.get("page_number")
            page_uuid = page_data.get("page_uuid")
            notebook_uuid = page_data.get("notebook_uuid")
            existing_block_id = page_data.get("existing_block_id")  # From SyncRecord for page
            existing_notebook_page_id = page_data.get("existing_notebook_page_id")  # From SyncRecord for notebook
            stale_block_ids = [b for b in (page_data.get("stale_block_ids") or []) if b]
            claimed = {_norm_id(b) for b in (page_data.get("claimed_block_ids") or []) if b}

            if not page_text.strip():
                return SyncResult(
                    status=SyncStatus.SKIPPED,
                    metadata={"reason": "Empty page content"},
                )

            if page_number is None:
                return SyncResult(
                    status=SyncStatus.FAILED,
                    error_message="Missing page_number in sync item data",
                )

            # Convert text to Notion blocks before any write, so an empty result
            # cannot leave behind a notebook page that nothing records.
            blocks = self._text_to_blocks(page_text, max_blocks=50)

            if not blocks:
                return SyncResult(
                    status=SyncStatus.SKIPPED,
                    metadata={"reason": "No blocks generated from content"},
                )

            # Track whether we created the notebook page in this sync
            notebook_created = False

            # First, try to use the notebook page ID from SyncRecord (database is source of truth)
            parent_page_id = existing_notebook_page_id

            # Fall back to searching Notion if no SyncRecord exists. This raises
            # on lookup failure; None means Notion confirmed there is no page.
            if not parent_page_id:
                parent_page_id = await self.find_existing_page(notebook_uuid)

            if not parent_page_id:
                # Auto-create the notebook page if it doesn't exist
                notebook_name = page_data.get("notebook_name", "Untitled Notebook")
                self.logger.info(f"Creating parent notebook page for {notebook_name} ({notebook_uuid})")

                parent_page_id = self._create_notebook_page(
                    notebook_uuid=notebook_uuid,
                    title=notebook_name,
                    full_path="",  # Don't have folder path from page data
                )

                notebook_created = True
                self.logger.info(f"Created new notebook page {parent_page_id} for {notebook_uuid}")

            page_toggle = self._build_page_toggle(page_number, page_uuid, blocks)

            # Old blocks an earlier update appended over but could not delete.
            stale_block_ids = [
                b for b in dict.fromkeys(stale_block_ids)
                if not self._delete_block(b, parent_page_id)
            ]

            children = self._list_children(parent_page_id)
            old_block_ids = self._blocks_to_replace(
                children, existing_block_id, page_uuid, page_number, claimed
            )
            insert_after_block_id = self._insertion_anchor(children, old_block_ids, page_number)

            # 1. Append the new toggle. Nothing has been removed yet, so a
            #    failure here leaves the page as it was.
            if insert_after_block_id:
                response = self._parent_call(
                    parent_page_id,
                    self.client.blocks.children.append,
                    block_id=parent_page_id,
                    children=[page_toggle],
                    after=insert_after_block_id,
                )
            else:
                response = self._parent_call(
                    parent_page_id,
                    self.client.blocks.children.append,
                    block_id=parent_page_id,
                    children=[page_toggle],
                )

            results = response.get("results") or []
            if not results or not results[0].get("id"):
                raise NotionSyncError(
                    SyncErrorKind.TRANSIENT, "Notion append returned no block id"
                )
            new_block_id = results[0]["id"]

            # 2. Delete what the new toggle replaces. The new id is returned to
            #    the worker either way; a block that could not be deleted is
            #    remembered so it does not become a permanent duplicate.
            for old_id in old_block_ids:
                if not self._delete_block(old_id, parent_page_id):
                    stale_block_ids.append(old_id)

            if existing_block_id:
                action = "page_updated"
            elif old_block_ids:
                action = "page_adopted"
            else:
                action = "page_created"
            self.logger.info(
                f"Page {page_number}: {action} (block {new_block_id}, "
                f"replaced {len(old_block_ids)}, stale {len(stale_block_ids)})"
            )

            return SyncResult(
                status=SyncStatus.SUCCESS,
                target_id=new_block_id,
                metadata={
                    "action": action,
                    "page_number": page_number,
                    "parent_page_id": parent_page_id,
                    "notebook_created": notebook_created,
                    "notebook_page_id": parent_page_id,
                    "stale_block_ids": stale_block_ids,
                },
            )

        except Exception as e:
            self.logger.error(f"Error syncing page text: {e}")
            return self._error_result(e)

    def _build_page_toggle(
        self, page_number: int, page_uuid: Optional[str], blocks: List[Dict]
    ) -> Dict:
        """Toggle block for one page: bold "📄 Page N" plus a small gray page marker."""
        rich_text = [
            {
                "type": "text",
                "text": {"content": f"📄 Page {page_number}"},
                "annotations": {"bold": True},
            }
        ]
        if page_uuid:
            rich_text.append(
                {
                    "type": "text",
                    "text": {"content": f"{_MARKER_PREFIX}{_page_marker(page_uuid)}"},
                    "annotations": {"color": "gray"},
                }
            )
        return {
            "object": "block",
            "type": "toggle",
            "toggle": {"rich_text": rich_text, "children": blocks},
        }

    def _parent_call(self, parent_page_id: str, func, *args, **kwargs):
        """Call ``func`` on the notebook page, reporting PARENT_GONE if it vanished.

        Notion answers "not found" or "archived" both when the notebook page
        itself is gone and when only a block we referenced (e.g. the ``after``
        anchor) is; the page is retrieved to tell the two apart.
        """
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            if not _is_gone(exc):
                raise
            if self._parent_is_gone(parent_page_id):
                raise NotionSyncError(
                    SyncErrorKind.PARENT_GONE,
                    f"Notion notebook page {parent_page_id} is archived or missing: {exc}",
                ) from exc
            # The page is fine; something it referenced changed under us.
            raise NotionSyncError(SyncErrorKind.TRANSIENT, str(exc)) from exc

    def _parent_is_gone(self, parent_page_id: str) -> bool:
        try:
            page = self.client.pages.retrieve(page_id=parent_page_id)
        except Exception as exc:
            if _is_gone(exc):
                return True
            raise
        return bool(page.get("archived") is True or page.get("in_trash") is True)

    def _list_children(self, parent_page_id: str) -> List[Dict]:
        """All top-level blocks of the notebook page."""
        all_blocks: List[Dict] = []
        start_cursor = None
        while True:
            if start_cursor:
                response = self._parent_call(
                    parent_page_id,
                    self.client.blocks.children.list,
                    block_id=parent_page_id,
                    start_cursor=start_cursor,
                )
            else:
                response = self._parent_call(
                    parent_page_id,
                    self.client.blocks.children.list,
                    block_id=parent_page_id,
                )

            all_blocks.extend(response.get("results", []))

            if not response.get("has_more", False):
                break
            start_cursor = response.get("next_cursor")
        return all_blocks

    def _blocks_to_replace(
        self,
        children: List[Dict],
        existing_block_id: Optional[str],
        page_uuid: Optional[str],
        page_number: int,
        claimed: set,
    ) -> List[str]:
        """Blocks on the notebook page that the new toggle for this page replaces.

        - the block the page's SyncRecord points at, if it is still there;
        - toggles carrying this page's marker that no other page's record
          claims (left by an attempt that appended but never got recorded);
        - for a page with no SyncRecord and no marked toggle, the first
          unclaimed, unmarked toggle titled exactly "📄 Page N" (toggles made
          before markers existed).

        Only blocks that are direct children of the notebook page are returned.
        """
        existing_norm = _norm_id(existing_block_id)
        replace: List[str] = []
        if existing_norm:
            for block in children:
                if _norm_id(block.get("id")) == existing_norm:
                    replace.append(block["id"])
                    break

        toggles = [
            b for b in children
            if b.get("type") == "toggle"
            and b.get("id")
            and _norm_id(b["id"]) not in claimed
            and _norm_id(b["id"]) != existing_norm
        ]
        if page_uuid:
            marker = _page_marker(page_uuid)
            replace.extend(b["id"] for b in toggles if _toggle_marker(b) == marker)

        if not existing_block_id and not replace:
            title = f"📄 Page {page_number}"
            for block in toggles:
                segments = _toggle_segments(block)
                if (
                    _toggle_marker(block) is None
                    and len(segments) == 1
                    and _segment_text(segments[0]) == title
                ):
                    replace.append(block["id"])
                    break
        return replace

    @staticmethod
    def _insertion_anchor(
        children: List[Dict], old_block_ids: List[str], page_number: int
    ) -> Optional[str]:
        """Block to append the new toggle after (None appends at the end).

        Replacing a block: right before the first block being replaced.
        Otherwise: reverse page order (highest page first), below the heading.
        """
        old = {_norm_id(b) for b in old_block_ids}
        for i, block in enumerate(children):
            if _norm_id(block.get("id")) in old:
                if i > 0:
                    return children[i - 1]["id"]
                break

        insert_after_block_id = None
        for block in children:
            if block.get("type") == "heading_2":
                insert_after_block_id = block["id"]
                break

        # Then find first page with HIGHER number
        for block in children:
            if block.get("type") != "toggle" or _norm_id(block.get("id")) in old:
                continue
            segments = _toggle_segments(block)
            if not segments:
                continue
            match = _PAGE_TITLE_RE.match(_segment_text(segments[0]))
            if match:
                block_page_num = int(match.group(1))
                if block_page_num > page_number:
                    insert_after_block_id = block["id"]
                elif block_page_num < page_number:
                    break
        return insert_after_block_id

    def _delete_block(self, block_id: str, parent_page_id: str) -> bool:
        """Delete a page toggle. True if it is gone (deleted, archived or missing)."""
        if _norm_id(block_id) == _norm_id(parent_page_id):
            # Never archive the notebook page itself through a stale block id.
            self.logger.warning(f"Refusing to delete notebook page {block_id} as a block")
            return True
        try:
            self.client.blocks.delete(block_id=block_id)
            return True
        except Exception as e:
            if _is_gone(e):
                self.logger.info(f"Block {block_id} already archived/deleted")
                return True
            self.logger.warning(f"Failed to delete old block {block_id}: {e}")
            return False


    def _extract_tags_from_path(self, full_path: str) -> List[str]:
        """
        Extract tags from folder path.

        Example: "Work/Projects/Client A" → ["Work", "Projects", "Client A"]

        Args:
            full_path: Full folder path with "/" separators

        Returns:
            List of tags (folder names)
        """
        if not full_path or full_path == "/":
            return []

        # Remove leading/trailing slashes and split
        path_parts = full_path.strip("/").split("/")

        # Filter out empty parts
        return [part for part in path_parts if part.strip()]

    async def find_existing_page(self, notebook_uuid: str) -> Optional[str]:
        """
        Find existing Notion page for a notebook UUID.

        Uses direct HTTP call to Notion's databases/query endpoint with an older
        API version (2022-06-28) because:
        - SDK 2025-09-03 removed databases.query() method
        - data_sources.query() doesn't work with databases created via databases.create()

        Args:
            notebook_uuid: Notebook UUID to search for

        Returns:
            Notion page ID if found; None only when Notion confirmed there is
            none (the query and the legacy title search both succeeded and
            matched nothing).

        Raises:
            NotionSyncError: the lookup failed (rate limit, auth, network,
                server error). Callers must not treat this as "not found",
                or they would create a duplicate notebook page.
        """
        # Use direct HTTP call with older API version that supports databases/query
        # The SDK's data_sources.query() doesn't work with our databases
        try:
            response = httpx.post(
                f"https://api.notion.com/v1/databases/{self.database_id}/query",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Notion-Version": "2022-06-28",  # Older version that supports this endpoint
                    "Content-Type": "application/json"
                },
                json={
                    "filter": {
                        "property": "UUID",
                        "rich_text": {
                            "equals": notebook_uuid
                        }
                    }
                },
                verify=self.verify_ssl,
                timeout=30.0
            )
        except httpx.HTTPError as e:
            raise NotionSyncError(
                SyncErrorKind.TRANSIENT, f"Notion database query failed: {e}"
            ) from e

        if response.status_code == 200:
            try:
                results = response.json().get("results", [])
            except ValueError as e:
                raise NotionSyncError(
                    SyncErrorKind.TRANSIENT, f"Notion database query returned invalid JSON: {e}"
                ) from e
            for result in results:
                if result.get("archived") is True or result.get("in_trash") is True:
                    continue
                page_id = result["id"]
                self.logger.info(f"Found existing page {page_id} for UUID {notebook_uuid}")
                return page_id
        elif response.status_code == 400:
            # This endpoint rejects some databases outright (bad request, not an
            # outage); the title search below is the lookup for those.
            self.logger.warning(f"Database query failed: {response.status_code} - {response.text[:200]}")
        else:
            try:
                code = response.json().get("code")
            except Exception:
                code = None
            raise _classify_status(
                response.status_code,
                code,
                response.headers,
                f"Notion database query failed with status {response.status_code}",
            )

        # Fallback: search by UUID prefix in title (for legacy pages)
        uuid_prefix = notebook_uuid[:8]
        try:
            search_response = self.client.search(
                query=uuid_prefix,
                filter={"property": "object", "value": "page"}
            )
        except Exception as e:
            err = classify_notion_error(e) or NotionSyncError(
                SyncErrorKind.TRANSIENT, f"Notion search failed: {e}"
            )
            raise err from e

        for result in search_response.get("results", []):
            if result.get("archived") is True or result.get("in_trash") is True:
                continue
            # Check both database_id formats (with and without dashes)
            parent = result.get("parent", {})
            parent_db_id = parent.get("database_id", "")
            # Normalize IDs for comparison (remove dashes)
            if parent_db_id.replace("-", "") == self.database_id.replace("-", ""):
                # Check if the title contains our UUID (legacy format)
                title_prop = result.get("properties", {}).get("Name", {})
                title_content = title_prop.get("title", [])
                if title_content:
                    title_text = title_content[0].get("text", {}).get("content", "")
                    if uuid_prefix in title_text:
                        return result["id"]

        return None

    @run_off_loop
    async def _create_notion_page(
        self, notebook_uuid: str, title: str, full_path: str,
        last_opened: Optional[str] = None, last_modified: Optional[str] = None
    ) -> Optional[str]:
        """
        Create a new, empty notebook page in the Notion database.

        Page toggles are added later by ``_sync_page_text``.

        Args:
            notebook_uuid: UUID of the notebook
            title: Title of the notebook
            full_path: Full folder path
            last_opened: When notebook was last opened on reMarkable (ISO 8601)
            last_modified: When notebook was last modified on reMarkable (ISO 8601)

        Returns:
            Notion page ID if successful, None otherwise
        """
        try:
            return self._create_notebook_page(
                notebook_uuid, title, full_path, last_opened, last_modified
            )
        except Exception as e:
            self.logger.error(f"Error creating Notion page: {e}")
            return None

    def _create_notebook_page(
        self, notebook_uuid: str, title: str, full_path: str,
        last_opened: Optional[str] = None, last_modified: Optional[str] = None
    ) -> str:
        """Create the notebook's (empty) page in the Notion database; raises on failure.

        The page holds only the "Notebook Content" heading; ``_sync_page_text``
        adds one toggle per page below it.
        """
        # Build page properties with all metadata
        properties = {
            "Name": {"title": [{"text": {"content": title}}]},
            "UUID": {"rich_text": [{"text": {"content": notebook_uuid}}]},
            "Path": {"rich_text": [{"text": {"content": full_path or ""}}]},
            "Pages": {"number": 0},
        }

        # Add Tags from path
        tags = self._extract_tags_from_path(full_path)
        if tags:
            properties["Tags"] = {"multi_select": [{"name": tag} for tag in tags]}

        # Add Last Opened if available
        if last_opened:
            try:
                properties["Last Opened"] = {"date": {"start": last_opened}}
            except Exception as e:
                self.logger.warning(f"Invalid last_opened format: {last_opened}, error: {e}")

        # Add Last Modified if available
        if last_modified:
            try:
                properties["Last Modified"] = {"date": {"start": last_modified}}
            except Exception as e:
                self.logger.warning(f"Invalid last_modified format: {last_modified}, error: {e}")

        # Add Synced At timestamp
        properties["Synced At"] = {"date": {"start": datetime.utcnow().isoformat()}}

        # Add Status
        properties["Status"] = {"select": {"name": "Synced"}}

        # Create the page with just the content heading
        response = self.client.pages.create(
            parent={"database_id": self.database_id},
            properties=properties,
            children=[
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [
                            {"type": "text", "text": {"content": "Notebook Content"}}
                        ]
                    },
                }
            ],
        )

        page_id = response["id"]
        self.logger.info(f"Created Notion page: {page_id} for notebook {title}")
        return page_id

    async def _update_notion_page_properties(
        self, page_id: str, notebook_uuid: str, title: str, page_count: int, full_path: str,
        last_opened: Optional[str] = None, last_modified: Optional[str] = None
    ) -> bool:
        """
        Update only Notion page properties (metadata) without touching content blocks.

        This is a lightweight operation for metadata-only updates.

        Args:
            page_id: Notion page ID
            notebook_uuid: UUID of the notebook
            title: Updated title
            page_count: Number of pages
            full_path: Updated folder path
            last_opened: When notebook was last opened on reMarkable (ISO 8601)
            last_modified: When notebook was last modified on reMarkable (ISO 8601)

        Returns:
            True if successful, False otherwise
        """
        try:
            from datetime import datetime

            # Build properties update
            properties = {
                "Name": {"title": [{"text": {"content": title}}]},
                "UUID": {"rich_text": [{"text": {"content": notebook_uuid}}]},
                "Path": {"rich_text": [{"text": {"content": full_path or ""}}]},
                "Pages": {"number": page_count},
                "Synced At": {"date": {"start": datetime.utcnow().isoformat()}},
                "Status": {"select": {"name": "Synced"}},
            }

            # Update Tags from path
            tags = self._extract_tags_from_path(full_path)
            if tags:
                properties["Tags"] = {"multi_select": [{"name": tag} for tag in tags]}
            else:
                properties["Tags"] = {"multi_select": []}

            # Update Last Opened if available
            if last_opened:
                try:
                    properties["Last Opened"] = {"date": {"start": last_opened}}
                except Exception as e:
                    self.logger.warning(f"Invalid last_opened format: {last_opened}, error: {e}")

            # Update Last Modified if available
            if last_modified:
                try:
                    properties["Last Modified"] = {"date": {"start": last_modified}}
                except Exception as e:
                    self.logger.warning(f"Invalid last_modified format: {last_modified}, error: {e}")

            # Update only properties (no content blocks)
            self.client.pages.update(page_id=page_id, properties=properties)
            self.logger.info(f"Updated metadata for Notion page {page_id}: {title}")

            return True

        except Exception as e:
            self.logger.error(f"Error updating Notion page properties: {e}")
            return False

    def _text_to_blocks(self, text: str, max_blocks: int = 100) -> List[Dict]:
        """
        Convert text with markdown to Notion blocks.

        Args:
            text: Text content to convert (may contain markdown)
            max_blocks: Maximum number of blocks to create

        Returns:
            List of Notion blocks with proper formatting
        """
        # Use the markdown converter to properly format text
        return self.markdown_converter.text_to_notion_blocks(text, max_blocks)

    async def check_duplicate(self, content_hash: str) -> Optional[str]:
        """Check if content with this hash already exists in Notion."""
        # For Notion, we use the notebook UUID as the primary identifier
        # Content hash checking is handled by the sync manager
        return None

    @run_off_loop
    async def update_item(self, external_id: str, item: SyncItem) -> SyncResult:
        """Not supported: page and metadata writes go through ``sync_item``."""
        return SyncResult(
            status=SyncStatus.FAILED,
            error_message=f"Update not supported for {item.item_type}",
        )

    @run_off_loop
    async def delete_item(self, external_id: str) -> SyncResult:
        """Delete (archive) an item from Notion."""
        try:
            # Notion doesn't really support deletion, but we can archive
            self.client.pages.update(page_id=external_id, archived=True)
            return SyncResult(
                status=SyncStatus.SUCCESS,
                metadata={
                    "action": "archived",
                    "note": "Notion pages archived, not deleted",
                },
            )
        except Exception as e:
            return SyncResult(status=SyncStatus.FAILED, error_message=str(e))

    @run_off_loop
    async def validate_connection(self) -> bool:
        """
        Validate connection to Notion.

        Returns:
            True if connection is valid, False otherwise
        """
        try:
            # Test connection by querying the database
            self.client.databases.retrieve(database_id=self.database_id)
            return True
        except Exception as e:
            self.logger.error(f"Failed to validate Notion connection: {e}")
            return False

    def get_target_info(self) -> Dict[str, Any]:
        """Get information about this Notion target."""
        try:
            # Test connection by querying the database
            response = self.client.databases.retrieve(database_id=self.database_id)

            return {
                "target_name": self.target_name,
                "connected": True,
                "database_id": self.database_id,
                "database_title": response.get("title", [{}])[0]
                .get("text", {})
                .get("content", "Unknown"),
                "capabilities": {
                    "notebooks": True,
                    "highlights": False,
                    "page_text": True,
                },
            }
        except Exception as e:
            return {
                "target_name": self.target_name,
                "connected": False,
                "error": str(e),
            }
