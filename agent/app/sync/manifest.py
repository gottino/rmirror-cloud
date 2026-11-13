"""
Persistent upload manifest.

A small SQLite file next to the agent's config file that remembers, per API
host and absolute file path, the size, mtime and sha256 of the last version
of each file the agent knows about, and when it was uploaded.

Entries come in two kinds:

- uploaded: the backend accepted this exact content (``uploaded_at`` is set).
- baseline: the file already existed when the manifest was first initialised
  for this API host, and was recorded without being uploaded
  (``uploaded_at`` is NULL). See ``scan_for_changes`` in
  ``app.watcher.file_watcher`` for why.

Either way, a file whose current sha256 equals its entry is "unchanged" and is
not uploaded again. Size + mtime are used as a cheap pre-check so unchanged
files are not re-hashed on every start-up scan.

Every call opens its own SQLite connection, so one instance can be shared by
the watchdog, Flask and asyncio threads.
"""

import hashlib
import logging
import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Union

from app.config import Config

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "upload_manifest.sqlite3"
_INITIALISED_KEY = "baseline_initialised_at"

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS files (
        api_host TEXT NOT NULL,
        path TEXT NOT NULL,
        size INTEGER NOT NULL,
        mtime_ns INTEGER NOT NULL,
        sha256 TEXT NOT NULL,
        uploaded_at TEXT,
        PRIMARY KEY (api_host, path)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meta (
        api_host TEXT NOT NULL,
        key TEXT NOT NULL,
        value TEXT,
        PRIMARY KEY (api_host, key)
    )
    """,
)


@dataclass(frozen=True)
class Fingerprint:
    """Size, mtime and content hash of a file at one point in time."""

    size: int
    mtime_ns: int
    sha256: str


@dataclass(frozen=True)
class ManifestEntry:
    """A row of the manifest."""

    path: str
    size: int
    mtime_ns: int
    sha256: str
    uploaded_at: str | None

    @property
    def is_baseline(self) -> bool:
        """True if the entry was recorded as a baseline and never uploaded."""
        return self.uploaded_at is None


def fingerprint_file(path: Union[str, Path]) -> Fingerprint:
    """Stat and hash a file. Raises OSError if it cannot be read."""
    st = os.stat(path)
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return Fingerprint(size=st.st_size, mtime_ns=st.st_mtime_ns, sha256=digest.hexdigest())


def _key(path: Union[str, Path]) -> str:
    return os.path.abspath(str(path))


class UploadManifest:
    """SQLite-backed record of uploaded (or baselined) file versions, per API host."""

    def __init__(self, db_path: Union[str, Path], api_host: Union[str, Callable[[], str]]):
        """
        Args:
            db_path: SQLite file to use (created on first use).
            api_host: Host name the entries belong to, or a callable returning it
                (so the manifest follows the agent when it is pointed at another backend).
        """
        self.db_path = Path(db_path)
        self._api_host = api_host
        self._schema_ready = False

    @classmethod
    def for_config(cls, config: Config) -> "UploadManifest":
        """Manifest in the config directory, namespaced like the keychain entry."""
        db_path = Config.get_default_config_path().parent / MANIFEST_FILENAME
        return cls(db_path, lambda: config.api._keychain_user_id)

    @property
    def api_host(self) -> str:
        host = self._api_host() if callable(self._api_host) else self._api_host
        return host or "default"

    def _connect(self) -> sqlite3.Connection:
        if not self._schema_ready:
            self.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        if not self._schema_ready:
            with conn:
                for statement in _SCHEMA:
                    conn.execute(statement)
            self._schema_ready = True
        return conn

    def _run(self, sql: str, params: tuple = ()) -> list[tuple]:
        conn = self._connect()
        try:
            with conn:
                return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Initialisation flag
    # ------------------------------------------------------------------

    def is_initialised(self) -> bool:
        """True once a baseline scan has completed for the current API host."""
        rows = self._run(
            "SELECT 1 FROM meta WHERE api_host = ? AND key = ?", (self.api_host, _INITIALISED_KEY)
        )
        return bool(rows)

    def mark_initialised(self) -> None:
        self._run(
            "INSERT OR REPLACE INTO meta (api_host, key, value) VALUES (?, ?, ?)",
            (self.api_host, _INITIALISED_KEY, _now()),
        )

    # ------------------------------------------------------------------
    # Entries
    # ------------------------------------------------------------------

    def get(self, path: Union[str, Path]) -> ManifestEntry | None:
        rows = self._run(
            "SELECT path, size, mtime_ns, sha256, uploaded_at FROM files WHERE api_host = ? AND path = ?",
            (self.api_host, _key(path)),
        )
        return ManifestEntry(*rows[0]) if rows else None

    def record_upload(self, path: Union[str, Path], fingerprint: Fingerprint) -> None:
        """Remember that the backend accepted this version of the file."""
        self._run(
            "INSERT OR REPLACE INTO files (api_host, path, size, mtime_ns, sha256, uploaded_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (self.api_host, _key(path), fingerprint.size, fingerprint.mtime_ns, fingerprint.sha256, _now()),
        )

    def record_baseline(self, path: Union[str, Path], fingerprint: Fingerprint) -> bool:
        """Record a file as baseline (not uploaded) unless it already has an entry.

        Returns True if a new entry was written.
        """
        conn = self._connect()
        try:
            with conn:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO files (api_host, path, size, mtime_ns, sha256, uploaded_at) "
                    "VALUES (?, ?, ?, ?, ?, NULL)",
                    (self.api_host, _key(path), fingerprint.size, fingerprint.mtime_ns, fingerprint.sha256),
                )
                return cur.rowcount > 0
        finally:
            conn.close()

    def _touch(self, path: Union[str, Path], fingerprint: Fingerprint) -> None:
        """Refresh size/mtime of an entry whose content hash still matches."""
        self._run(
            "UPDATE files SET size = ?, mtime_ns = ? WHERE api_host = ? AND path = ? AND sha256 = ?",
            (fingerprint.size, fingerprint.mtime_ns, self.api_host, _key(path), fingerprint.sha256),
        )

    def changed_fingerprint(self, path: Union[str, Path]) -> Fingerprint | None:
        """Compare a file with its manifest entry.

        Returns None if the file is unchanged (same sha256 as the entry), otherwise
        the file's current fingerprint (also when it has no entry yet). Size and
        mtime are checked first so unchanged files are not hashed.

        Raises:
            OSError: if the file cannot be read (for example it was deleted).
        """
        entry = self.get(path)
        if entry is not None:
            st = os.stat(path)
            if st.st_size == entry.size and st.st_mtime_ns == entry.mtime_ns:
                return None
        current = fingerprint_file(path)
        if entry is not None and current.sha256 == entry.sha256:
            self._touch(path, current)
            return None
        return current


def _now() -> str:
    return datetime.now(UTC).isoformat()
