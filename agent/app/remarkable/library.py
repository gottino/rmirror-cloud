"""
Read-only views of the reMarkable Desktop folder for the local API v2.

- ``folder_state``: whether the folder exists and can be listed.
- ``scan_documents``: a flat list of notebooks with their folder path, page
  count and timestamps (no folders, no trashed items, no PDFs/EPUBs, which the
  sync does not upload either).

Both only read ``.metadata`` / ``.content`` JSON files and directory listings.
"""

import errno
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)

FOLDER_OK = "ok"
FOLDER_MISSING = "missing"
FOLDER_UNREADABLE = "unreadable"

_MISSING_ERRNOS = {errno.ENOENT, errno.ENOTDIR}

TRASH_PARENT = "trash"


def folder_state(path: Union[str, Path]) -> str:
    """``ok``, ``missing`` (does not exist / not a folder) or ``unreadable``.

    ``unreadable`` means the path exists but listing it fails, typically with
    EPERM because macOS privacy protection (Full Disk Access) blocks it.
    """
    try:
        with os.scandir(path) as entries:
            next(entries, None)
    except OSError as e:
        if e.errno in _MISSING_ERRNOS:
            return FOLDER_MISSING
        if isinstance(e, PermissionError) or e.errno in (errno.EPERM, errno.EACCES):
            return FOLDER_UNREADABLE
        return FOLDER_UNREADABLE if os.path.lexists(path) else FOLDER_MISSING
    return FOLDER_OK


@dataclass
class DocumentInfo:
    """One notebook in the reMarkable folder."""

    uuid: str
    name: str
    folder_path: list[str] = field(default_factory=list)
    document_type: str = "notebook"
    page_count: int = 0
    last_opened_at: datetime | None = None
    last_modified_at: datetime | None = None

    @property
    def recency(self) -> datetime:
        """Last opened, falling back to last modified (for "most recent first")."""
        return self.last_opened_at or self.last_modified_at or datetime.min.replace(tzinfo=UTC)


def _timestamp(value: object) -> datetime | None:
    """reMarkable millisecond timestamp (string or number) -> aware UTC datetime; 0/invalid -> None."""
    try:
        ms = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000.0, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _page_count(content_file: Path) -> int:
    try:
        with open(content_file) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return 0
    if not isinstance(data, dict):
        return 0
    count = data.get("pageCount")
    if isinstance(count, int) and count >= 0:
        return count
    pages = data.get("pages")
    if isinstance(pages, list) and pages:
        return len(pages)
    c_pages = data.get("cPages")
    if isinstance(c_pages, dict) and isinstance(c_pages.get("pages"), list):
        return sum(
            1
            for page in c_pages["pages"]
            if not (isinstance(page, dict) and isinstance(page.get("deleted"), dict) and page["deleted"].get("value"))
        )
    return 0


def scan_documents(folder: Union[str, Path]) -> list[DocumentInfo]:
    """All notebooks in the folder, unsorted. Blocking (reads files); never raises for one bad file."""
    root = Path(folder)
    collections: dict[str, tuple[str, str]] = {}  # uuid -> (name, parent)
    candidates: list[tuple[Path, dict]] = []

    for metadata_file in root.glob("*.metadata"):
        try:
            with open(metadata_file) as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            logger.debug(f"Skipping unreadable metadata file {metadata_file.name}: {e}")
            continue
        if not isinstance(data, dict):
            continue
        uuid = metadata_file.stem
        doc_type = data.get("type", "DocumentType")
        parent = data.get("parent") or ""
        if doc_type == "CollectionType":
            collections[uuid] = (str(data.get("visibleName", "")), str(parent))
        elif doc_type == "DocumentType":
            candidates.append((metadata_file, data))

    def folder_chain(parent: str) -> list[str] | None:
        """Names from the top folder down to parent; None if the item is in the trash."""
        names: list[str] = []
        seen: set[str] = set()
        while parent:
            if parent == TRASH_PARENT:
                return None
            if parent in seen or parent not in collections:
                break
            seen.add(parent)
            name, parent = collections[parent]
            names.append(name)
        names.reverse()
        return names

    documents: list[DocumentInfo] = []
    for metadata_file, data in candidates:
        if data.get("deleted") is True:
            continue
        # PDFs and EPUBs are not uploaded by the sync (see MetadataScanner)
        if metadata_file.with_suffix(".pdf").exists() or metadata_file.with_suffix(".epub").exists():
            continue
        path = folder_chain(str(data.get("parent") or ""))
        if path is None:
            continue
        documents.append(
            DocumentInfo(
                uuid=metadata_file.stem,
                name=str(data.get("visibleName", "Untitled")),
                folder_path=path,
                page_count=_page_count(metadata_file.with_suffix(".content")),
                last_opened_at=_timestamp(data.get("lastOpened")),
                last_modified_at=_timestamp(data.get("lastModified")),
            )
        )
    return documents


def count_page_files(folder: Union[str, Path], notebook_uuid: str) -> int:
    """Number of .rm page files in a notebook's directory (0 if it has none)."""
    try:
        return sum(1 for _ in (Path(folder) / notebook_uuid).glob("*.rm"))
    except OSError:
        return 0
