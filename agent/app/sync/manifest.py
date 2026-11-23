"""
Persistent upload manifest.

A small SQLite file next to the agent's config file that remembers, per API
host and absolute file path, the size, mtime and sha256 of the last version
of each file the agent knows about, and when it was uploaded.

Entries come in two kinds:

- uploaded: the backend accepted this exact content (``uploaded_at`` is set).
- baseline: the file was recorded without being uploaded (``uploaded_at`` is
  NULL): a file the first contact with this API host left out (see
  ``app.sync.catch_up``), a file of a notebook that is not selected, or a file
  in a folder the user switched to.

Per API host the ``meta`` table also holds whether the host is initialised,
the account (lower-cased e-mail) the entries belong to, the outcome of the
first-contact catch-up and the selection-notice flag; ``server_notebooks``
remembers which notebooks the server had pages for at that catch-up.

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
ACCOUNT_KEY = "account"
CATCH_UP_KEY = "catch_up"
NOTICE_KEY = "selection_notice"

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
    """
    CREATE TABLE IF NOT EXISTS server_notebooks (
        api_host TEXT NOT NULL,
        notebook_uuid TEXT NOT NULL,
        PRIMARY KEY (api_host, notebook_uuid)
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

    def for_host(self, api_host: str) -> "UploadManifest":
        """The same file, pinned to one host (not following later config changes)."""
        pinned = UploadManifest(self.db_path, api_host)
        pinned._schema_ready = self._schema_ready
        return pinned

    def _connect(self) -> sqlite3.Connection:
        if not self._schema_ready:
            self.db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        if not self._schema_ready:
            with conn:
                for statement in _SCHEMA:
                    conn.execute(statement)
                columns = {row[1] for row in conn.execute("PRAGMA table_info(files)")}
                if "via_catch_up" not in columns:
                    # 1 = recorded as uploaded because the server already had this
                    # version (first-contact catch-up), not uploaded by this agent
                    conn.execute("ALTER TABLE files ADD COLUMN via_catch_up INTEGER NOT NULL DEFAULT 0")
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
    # Per-host meta: account binding, catch-up outcome, selection notice
    # ------------------------------------------------------------------

    def get_meta(self, key: str) -> str | None:
        rows = self._run("SELECT value FROM meta WHERE api_host = ? AND key = ?", (self.api_host, key))
        return rows[0][0] if rows else None

    def set_meta(self, key: str, value: str) -> None:
        self._run(
            "INSERT OR REPLACE INTO meta (api_host, key, value) VALUES (?, ?, ?)", (self.api_host, key, value)
        )

    def account(self) -> str | None:
        """The account (lower-cased e-mail) this host's entries belong to; None if not recorded."""
        return self.get_meta(ACCOUNT_KEY)

    def set_account(self, email: str) -> None:
        self.set_meta(ACCOUNT_KEY, email.strip().lower())

    def has_entries(self) -> bool:
        return bool(self._run("SELECT 1 FROM files WHERE api_host = ? LIMIT 1", (self.api_host,)))

    def reset_host(self) -> int:
        """Forget every file entry, meta value and server notebook of the current host.

        Other hosts are not touched. Returns the number of file entries removed.
        """
        conn = self._connect()
        try:
            with conn:
                removed = conn.execute("DELETE FROM files WHERE api_host = ?", (self.api_host,)).rowcount
                conn.execute("DELETE FROM meta WHERE api_host = ?", (self.api_host,))
                conn.execute("DELETE FROM server_notebooks WHERE api_host = ?", (self.api_host,))
                return removed
        finally:
            conn.close()

    def server_notebooks(self) -> set[str]:
        """Notebook UUIDs the server had pages for at the first-contact catch-up (empty if unknown)."""
        rows = self._run("SELECT notebook_uuid FROM server_notebooks WHERE api_host = ?", (self.api_host,))
        return {row[0] for row in rows}

    def fingerprints_elsewhere(self) -> dict[str, list[Fingerprint]]:
        """Fingerprints recorded for each path under other hosts (to avoid re-hashing a file)."""
        rows = self._run(
            "SELECT path, size, mtime_ns, sha256 FROM files WHERE api_host != ?", (self.api_host,)
        )
        known: dict[str, list[Fingerprint]] = {}
        for path, size, mtime_ns, sha256 in rows:
            known.setdefault(path, []).append(Fingerprint(size=size, mtime_ns=mtime_ns, sha256=sha256))
        return known

    def paths_with_entries(self) -> set[str]:
        """Every path that has an entry (uploaded or baseline) for the current host."""
        return {row[0] for row in self._run("SELECT path FROM files WHERE api_host = ?", (self.api_host,))}

    def uploaded_paths(self) -> set[str]:
        """Every path recorded as uploaded for the current host."""
        rows = self._run(
            "SELECT path FROM files WHERE api_host = ? AND uploaded_at IS NOT NULL", (self.api_host,)
        )
        return {row[0] for row in rows}

    def apply_catch_up(
        self,
        *,
        uploaded: list[tuple[Union[str, Path], Fingerprint]],
        baselines: list[tuple[Union[str, Path], Fingerprint]],
        server_notebooks: set[str],
        state: str,
        account: str | None,
        notice: str | None,
    ) -> None:
        """Write the result of a first-contact catch-up in one transaction and mark the host initialised.

        Entries that already exist are kept (INSERT OR IGNORE): the catch-up only
        fills in files the manifest knows nothing about for this host.
        """
        host = self.api_host
        now = _now()
        conn = self._connect()
        try:
            with conn:
                conn.executemany(
                    "INSERT OR IGNORE INTO files (api_host, path, size, mtime_ns, sha256, uploaded_at, via_catch_up) "
                    "VALUES (?, ?, ?, ?, ?, ?, 1)",
                    [(host, _key(p), fp.size, fp.mtime_ns, fp.sha256, now) for p, fp in uploaded],
                )
                conn.executemany(
                    "INSERT OR IGNORE INTO files (api_host, path, size, mtime_ns, sha256, uploaded_at) "
                    "VALUES (?, ?, ?, ?, ?, NULL)",
                    [(host, _key(p), fp.size, fp.mtime_ns, fp.sha256) for p, fp in baselines],
                )
                conn.execute("DELETE FROM server_notebooks WHERE api_host = ?", (host,))
                conn.executemany(
                    "INSERT OR IGNORE INTO server_notebooks (api_host, notebook_uuid) VALUES (?, ?)",
                    [(host, uuid) for uuid in sorted(server_notebooks)],
                )
                meta = {_INITIALISED_KEY: now, CATCH_UP_KEY: state}
                if account:
                    meta[ACCOUNT_KEY] = account.strip().lower()
                if notice:
                    meta[NOTICE_KEY] = notice
                conn.executemany(
                    "INSERT OR REPLACE INTO meta (api_host, key, value) VALUES (?, ?, ?)",
                    [(host, key, value) for key, value in meta.items()],
                )
        finally:
            conn.close()

    def apply_upgrade(
        self,
        *,
        uploaded: list[tuple[Union[str, Path], Fingerprint]],
        server_notebooks: set[str],
        state: str,
        notice: str | None,
    ) -> None:
        """Upgrade a host initialised without the server's list (fallback) once the list is known.

        Records ``uploaded`` (files whose current version the server holds) as
        uploaded by the catch-up, replacing baseline entries or filling gaps; never
        removes a record and never touches files recorded as uploaded already.
        """
        host = self.api_host
        now = _now()
        conn = self._connect()
        try:
            with conn:
                for p, fp in uploaded:
                    key = _key(p)
                    row = conn.execute(
                        "SELECT uploaded_at FROM files WHERE api_host = ? AND path = ?", (host, key)
                    ).fetchone()
                    if row is not None and row[0] is not None:
                        continue
                    conn.execute(
                        "INSERT OR REPLACE INTO files "
                        "(api_host, path, size, mtime_ns, sha256, uploaded_at, via_catch_up) "
                        "VALUES (?, ?, ?, ?, ?, ?, 1)",
                        (host, key, fp.size, fp.mtime_ns, fp.sha256, now),
                    )
                conn.execute("DELETE FROM server_notebooks WHERE api_host = ?", (host,))
                conn.executemany(
                    "INSERT OR IGNORE INTO server_notebooks (api_host, notebook_uuid) VALUES (?, ?)",
                    [(host, uuid) for uuid in sorted(server_notebooks)],
                )
                meta = {CATCH_UP_KEY: state}
                if notice:
                    meta[NOTICE_KEY] = notice
                conn.executemany(
                    "INSERT OR REPLACE INTO meta (api_host, key, value) VALUES (?, ?, ?)",
                    [(host, key, value) for key, value in meta.items()],
                )
        finally:
            conn.close()

    def entries(self) -> dict[str, ManifestEntry]:
        """Every entry of the current host, by path."""
        rows = self._run(
            "SELECT path, size, mtime_ns, sha256, uploaded_at FROM files WHERE api_host = ?", (self.api_host,)
        )
        return {row[0]: ManifestEntry(*row) for row in rows}

    def has_uploaded_pages(self) -> bool:
        """True if any page (.rm) is recorded as uploaded for the current host (catch-up included)."""
        rows = self._run(
            "SELECT 1 FROM files WHERE api_host = ? AND uploaded_at IS NOT NULL AND path LIKE ? LIMIT 1",
            (self.api_host, "%.rm"),
        )
        return bool(rows)

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

    def forget_baseline(self, path: Union[str, Path]) -> bool:
        """Remove a file's baseline entry (never uploaded), so the next scan uploads it.

        Entries of uploaded files are kept. Returns True if an entry was removed.
        """
        conn = self._connect()
        try:
            with conn:
                cur = conn.execute(
                    "DELETE FROM files WHERE api_host = ? AND path = ? AND uploaded_at IS NULL",
                    (self.api_host, _key(path)),
                )
                return cur.rowcount > 0
        finally:
            conn.close()

    def last_upload_at(self) -> str | None:
        """When this agent last uploaded a file for the current API host (None: never).

        Records made by the first-contact catch-up (the server already had the
        file) are not uploads and are ignored.
        """
        rows = self._run(
            "SELECT MAX(uploaded_at) FROM files WHERE api_host = ? AND uploaded_at IS NOT NULL "
            "AND via_catch_up = 0",
            (self.api_host,),
        )
        return rows[0][0] if rows else None

    def forget_notebook(self, source_dir: Union[str, Path], notebook_uuid: str) -> int:
        """Remove every entry (uploaded or baseline) of one notebook's files for the current host.

        Its page directory (``<source>/<uuid>/...``) and its ``<uuid>.*`` files
        (``.metadata``, ``.content``, ...). Afterwards they count as never seen, so the
        next rescan uploads them (if the notebook is selected). Returns the rows removed.
        """
        root = _key(source_dir)
        page_prefix = os.path.join(root, notebook_uuid) + os.sep
        file_prefix = os.path.join(root, notebook_uuid) + "."
        conn = self._connect()
        try:
            with conn:
                cur = conn.execute(
                    "DELETE FROM files WHERE api_host = ? AND ("
                    "substr(path, 1, ?) = ? OR (substr(path, 1, ?) = ? AND instr(substr(path, ?), ?) = 0))",
                    (
                        self.api_host,
                        len(page_prefix), page_prefix,
                        len(file_prefix), file_prefix, len(file_prefix) + 1, os.sep,
                    ),
                )
                return cur.rowcount
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
