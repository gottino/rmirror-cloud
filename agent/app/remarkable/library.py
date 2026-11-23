"""
Read-only views of the reMarkable Desktop folder for the local API v2.

- ``folder_state``: whether the folder exists and can be listed.
- ``scan_library``: the notebooks (folder path, parent folder uuid, page count
  and timestamps; no trashed items, no PDFs/EPUBs, which the sync does not
  upload either) plus the folders that are not in the trash, in one pass.
- ``scan_documents``: just the notebooks of ``scan_library``.

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
    parent_uuid: str | None = None
    document_type: str = "notebook"
    page_count: int = 0
    last_opened_at: datetime | None = None
    last_modified_at: datetime | None = None

    @property
    def recency(self) -> datetime:
        """Last opened, falling back to last modified (for "most recent first")."""
        return self.last_opened_at or self.last_modified_at or datetime.min.replace(tzinfo=UTC)


@dataclass
class FolderInfo:
    """One folder (not in the trash). ``parent_uuid`` is None at the top level."""

    uuid: str
    name: str
    parent_uuid: str | None = None


@dataclass
class Library:
    documents: list[DocumentInfo] = field(default_factory=list)
    folders: list[FolderInfo] = field(default_factory=list)


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


def scan_library(folder: Union[str, Path]) -> Library:
    """Notebooks and folders in one pass. Blocking (reads files); never raises for one bad file.

    Documents are unsorted; folders are sorted by name (case-insensitive), then uuid.
    """
    root = Path(folder)
    # uuid -> (raw visibleName, parent, deleted)
    collections: dict[str, tuple[str, str, bool]] = {}
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
            collections[uuid] = (str(data.get("visibleName", "")), str(parent), data.get("deleted") is True)
        elif doc_type == "DocumentType":
            candidates.append((metadata_file, data))

    def folder_chain(parent: str) -> list[str]:
        """Names from the top folder down to parent."""
        names: list[str] = []
        seen: set[str] = set()
        while parent:
            if parent in seen or parent not in collections:
                break
            seen.add(parent)
            name, parent, _ = collections[parent]
            names.append(name)
        names.reverse()
        return names

    def in_trash(parent: str) -> bool:
        """True if the folder ``parent`` (or an ancestor) is trashed, or ``parent`` is the trash."""
        seen: set[str] = set()
        while parent:
            if parent == TRASH_PARENT:
                return True
            if parent in seen or parent not in collections:
                return False
            seen.add(parent)
            _, next_parent, deleted = collections[parent]
            if deleted:
                return True
            parent = next_parent
        return False

    def on_cycle(uuid: str) -> bool:
        seen: set[str] = set()
        cur = collections[uuid][1]
        while cur in collections and cur not in seen:
            if cur == uuid:
                return True
            seen.add(cur)
            cur = collections[cur][1]
        return False

    folders: list[FolderInfo] = []
    for uuid, (name, parent, _deleted) in collections.items():
        if in_trash(uuid):
            continue
        # A missing parent or a parent loop makes the folder top-level
        parent_uuid = parent if parent in collections and not on_cycle(uuid) else None
        folders.append(FolderInfo(uuid=uuid, name=name or "Untitled", parent_uuid=parent_uuid))
    folders.sort(key=lambda f: (f.name.casefold(), f.uuid))
    listed = {f.uuid for f in folders}

    documents: list[DocumentInfo] = []
    for metadata_file, data in candidates:
        if data.get("deleted") is True:
            continue
        # PDFs and EPUBs are not uploaded by the sync (see MetadataScanner)
        if metadata_file.with_suffix(".pdf").exists() or metadata_file.with_suffix(".epub").exists():
            continue
        parent = str(data.get("parent") or "")
        if in_trash(parent):
            continue
        documents.append(
            DocumentInfo(
                uuid=metadata_file.stem,
                name=str(data.get("visibleName", "Untitled")),
                folder_path=folder_chain(parent),
                parent_uuid=parent if parent in listed else None,
                page_count=_page_count(metadata_file.with_suffix(".content")),
                last_opened_at=_timestamp(data.get("lastOpened")),
                last_modified_at=_timestamp(data.get("lastModified")),
            )
        )
    return Library(documents=documents, folders=folders)


def scan_documents(folder: Union[str, Path]) -> list[DocumentInfo]:
    """All notebooks in the folder, unsorted. Blocking (reads files); never raises for one bad file."""
    return scan_library(folder).documents


def count_page_files(folder: Union[str, Path], notebook_uuid: str) -> int:
    """Number of .rm page files in a notebook's directory (0 if it has none)."""
    try:
        return sum(1 for _ in (Path(folder) / notebook_uuid).glob("*.rm"))
    except OSError:
        return 0
