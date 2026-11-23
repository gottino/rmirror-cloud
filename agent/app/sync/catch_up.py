"""
First contact with an API host: ask the server what it already has ("catch-up").

The upload manifest alone decides whether a file is uploaded. The first time the
agent works with an API host for an account the manifest has nothing for it, so
it cannot tell "already on the server" from "never uploaded". Instead of only
recording every existing file as a blind baseline (which silently dropped
everything that changed while rMirror was not syncing: server switch, reinstall,
long gap), the agent asks ``GET /sync/stored-pages`` and reconciles:

1. A local ``.rm`` page whose (notebook, page) the server lists with the same
   SHA-256 and a status other than ``failed`` / ``not_synced`` is recorded as
   **uploaded** (flagged as a catch-up record, not an upload), in every notebook.
2. Only with an explicit selection (``sync_all_notebooks`` false), in selected,
   non-excluded notebooks, files are left **without a record** so the watcher's
   next scan uploads them through the sync queue:
   - pages a sync would upload (the newest ``max_pages_per_notebook``, as
     ``PagePlanner`` picks them), and pages beyond the limit that the server
     holds in a different version (so the server's copy follows the file);
   - the notebook's ``.metadata`` / ``.content``, but only if the server has the
     notebook or at least one of its pages is left to upload (otherwise the
     upload would answer ``notebook_not_found`` on every scan).
3. Everything else is baselined as before: all of it when there is no explicit
   selection (``sync_all_notebooks`` true: a fresh install must not upload and
   OCR the whole library at sign-in), unselected and excluded notebooks, pages
   beyond the limit the server does not have, folder ``.metadata`` files and any
   file type other than ``.rm`` / ``.metadata`` / ``.content``.
4. The host is marked initialised for the signed-in account, with the set of
   notebooks the server has pages for and, if some of those are not selected
   here, a pending selection notice.

Failure handling: an older backend (FastAPI's own 404/405 for the route), any
other 4xx and a malformed answer use the same rules with an empty server list
(state ``unavailable``); so do network errors, 429 and 5xx once they have lasted
``GIVE_UP_SECONDS`` (before that they are retried with backoff and nothing is
recorded or uploaded for the host). 401 takes the existing sign-in-required
path. A host initialised as ``unavailable`` asks the server again once per
watcher start and is upgraded to ``done`` when that works (records only added).

The manifest is bound to an account (e-mail): when another account signs in on
the same host, that host's entries are forgotten and the catch-up runs again.
"""

import asyncio
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import Config
from app.remarkable.library import FOLDER_OK, folder_state
from app.sync.cloud_sync import (
    AuthenticationRequiredError,
    CloudSyncError,
    StoredPagesUnavailableError,
)
from app.sync.manifest import (
    ACCOUNT_KEY,
    CATCH_UP_KEY,
    NOTICE_KEY,
    Fingerprint,
    UploadManifest,
    fingerprint_file,
)

logger = logging.getLogger(__name__)

# catch_up.state in GET /api/v2/state
CATCH_UP_PENDING = "pending"
CATCH_UP_DONE = "done"
CATCH_UP_UNAVAILABLE = "unavailable"
CATCH_UP_NOT_NEEDED = "not_needed"

# Selection notice flag (manifest meta, per host)
NOTICE_PENDING = "pending"
NOTICE_CLEARED = "cleared"

# Server page statuses for which the server re-processes an identical upload:
# such pages are not counted as being on the server
REPROCESSED_STATUSES = frozenset({"failed", "not_synced"})


def normalise_email(value: object) -> str | None:
    """Lower-cased e-mail, or None when unknown (also for non-strings, e.g. test doubles)."""
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    return None


@dataclass
class ServerPages:
    """The parsed answer of ``GET /sync/stored-pages``."""

    # (notebook_uuid, page_uuid) -> (sha256 or None, ocr_status)
    pages: dict[tuple[str, str], tuple[str | None, str]] = field(default_factory=dict)
    # Notebooks with at least one page on the server
    notebooks: set[str] = field(default_factory=set)

    def has_current(self, notebook_uuid: str, page_uuid: str, sha256: str) -> bool:
        """True if the server holds exactly this version and will not re-process it."""
        entry = self.pages.get((notebook_uuid, page_uuid))
        if entry is None:
            return False
        server_hash, status = entry
        return server_hash == sha256 and status not in REPROCESSED_STATUSES


def parse_stored_pages(data: Any) -> ServerPages:
    """Validate and index a stored-pages response. Raises ValueError if it has the wrong shape."""
    if not isinstance(data, dict) or not isinstance(data.get("notebooks"), list):
        raise ValueError("stored-pages: 'notebooks' list missing")
    result = ServerPages()
    for notebook in data["notebooks"]:
        if not isinstance(notebook, dict) or not isinstance(notebook.get("notebook_uuid"), str):
            raise ValueError("stored-pages: notebook without notebook_uuid")
        pages = notebook.get("pages") or []
        if not isinstance(pages, list):
            raise ValueError("stored-pages: pages is not a list")
        uuid = notebook["notebook_uuid"]
        for page in pages:
            if not isinstance(page, dict) or not isinstance(page.get("page_uuid"), str):
                raise ValueError("stored-pages: page without page_uuid")
            file_hash = page.get("file_hash")
            status = page.get("ocr_status")
            result.pages[(uuid, page["page_uuid"])] = (
                file_hash.lower() if isinstance(file_hash, str) and file_hash else None,
                status if isinstance(status, str) else "",
            )
            result.notebooks.add(uuid)
    return result


@dataclass
class ReconcileResult:
    uploaded: int = 0
    baselined: int = 0
    left_for_upload: int = 0
    unselected_on_server: int = 0


def _leaves_without_record(config: Config, uuid: str) -> bool:
    """Only an explicit selection leaves files without a record on first contact."""
    if config.sync.sync_all_notebooks or uuid in config.sync.excluded_notebooks:
        return False
    return uuid in config.sync.selected_notebooks


def unselected_on_server_count(config: Config, source_dir: str | Path, server_notebooks: set[str]) -> int:
    """Local, non-excluded notebooks the server had pages for that are not selected now.

    0 while everything is synced (``sync_all``): the notebook list then shows every
    notebook as selected, so there is nothing unticked to point at.
    """
    if config.sync.sync_all_notebooks or not server_notebooks:
        return 0
    excluded = set(config.sync.excluded_notebooks)
    selected = set(config.sync.selected_notebooks)
    root = Path(source_dir)
    return sum(
        1
        for uuid in server_notebooks
        if uuid not in excluded and uuid not in selected and (root / f"{uuid}.metadata").exists()
    )


# File types that may be left without a record on first contact
_LEAVABLE_NOTEBOOK_FILES = (".metadata", ".content")


def _folder_files(root: Path, handler: Any) -> list[tuple[Path, str, str]]:
    """(path, abspath, notebook uuid) of every file the watcher considers."""
    result = []
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            path = Path(dirpath) / name
            if handler._should_ignore_file(str(path)):
                continue
            uuid = handler._extract_notebook_uuid(path)
            if uuid:
                result.append((path, os.path.abspath(str(path)), uuid))
    return result


def _is_page(key: str, root_key: str) -> bool:
    return key.endswith(".rm") and os.path.dirname(os.path.dirname(key)) == root_key


def reconcile_folder(
    source_dir: Path,
    handler: Any,
    manifest: UploadManifest,
    config: Config,
    server: ServerPages | None,
    account: str | None,
) -> ReconcileResult:
    """Apply the first-contact rules (module docstring) to the folder and initialise the host.

    ``handler`` provides the watcher's file filters (``_should_ignore_file``,
    ``_extract_notebook_uuid``), so exactly the files the watcher considers are
    looked at. ``server`` None means the server's list is not available (fallback).
    ``manifest`` should be pinned to one host (``for_host``). Files that already
    have an entry for this host keep it. Blocking (stats and hashes files): run it
    off the event loop. Writes everything in one transaction at the end.
    """
    from app.sync.initial_sync import PagePlanner

    root = Path(source_dir)
    root_key = os.path.abspath(str(root))
    existing = manifest.paths_with_entries()
    elsewhere = manifest.fingerprints_elsewhere()
    planner = PagePlanner(config, manifest)
    planner.remarkable_folder = root
    within_limit: dict[str, set[str]] = {}

    def pages_within_limit(uuid: str) -> set[str]:
        if uuid not in within_limit:
            within, _beyond = planner._limit_pages(uuid, log=False)
            within_limit[uuid] = {os.path.abspath(str(p)) for p in within}
        return within_limit[uuid]

    def fingerprint(path: Path, key: str) -> Fingerprint:
        st = os.stat(path)
        for known in elsewhere.get(key, ()):
            if known.size == st.st_size and known.mtime_ns == st.st_mtime_ns:
                return known
        return fingerprint_file(path)

    uploaded: list[tuple[Path, Fingerprint]] = []
    baselines: list[tuple[Path, Fingerprint]] = []
    result = ReconcileResult()
    files = [entry for entry in _folder_files(root, handler) if entry[1] not in existing]
    notebooks_with_uploads: set[str] = set()

    # Pages first: whether a notebook has a page to upload decides its .metadata/.content
    for path, key, uuid in files:
        if not _is_page(key, root_key):
            continue
        try:
            fp = None
            listed = server.pages.get((uuid, path.stem)) if server is not None else None
            if listed is not None:
                fp = fingerprint(path, key)
                if server.has_current(uuid, path.stem, fp.sha256):
                    uploaded.append((path, fp))
                    result.uploaded += 1
                    continue
            if _leaves_without_record(config, uuid) and (
                key in pages_within_limit(uuid)
                # Beyond the limit but the server holds another version: follow the file
                or (listed is not None and listed[0] != fp.sha256)
            ):
                result.left_for_upload += 1
                notebooks_with_uploads.add(uuid)
                continue
            baselines.append((path, fp or fingerprint(path, key)))
            result.baselined += 1
        except OSError as e:
            logger.debug(f"Skipping unreadable file during catch-up: {path}: {e}")

    server_has = server.notebooks if server is not None else set()
    for path, key, uuid in files:
        if _is_page(key, root_key):
            continue
        try:
            if (
                path.suffix in _LEAVABLE_NOTEBOOK_FILES
                and _leaves_without_record(config, uuid)
                and (uuid in server_has or uuid in notebooks_with_uploads)
            ):
                # Uploaded once, so renames and moves made meanwhile arrive
                result.left_for_upload += 1
                continue
            baselines.append((path, fingerprint(path, key)))
            result.baselined += 1
        except OSError as e:
            logger.debug(f"Skipping unreadable file during catch-up: {path}: {e}")

    result.unselected_on_server = unselected_on_server_count(config, root, server_has)
    manifest.apply_catch_up(
        uploaded=uploaded,
        baselines=baselines,
        server_notebooks=server_has,
        state=CATCH_UP_DONE if server is not None else CATCH_UP_UNAVAILABLE,
        account=account,
        notice=NOTICE_PENDING if result.unselected_on_server else None,
    )
    logger.info(
        f"Catch-up with {manifest.api_host}: {result.uploaded} file(s) already on the server, "
        f"{result.left_for_upload} left to upload, {result.baselined} recorded as baseline"
        + ("" if server is not None else " (without the server's list)")
    )
    return result


def upgrade_folder(
    source_dir: Path, handler: Any, manifest: UploadManifest, config: Config, server: ServerPages
) -> int:
    """A host initialised without the server's list (``unavailable``) gets it now.

    Every page whose current version the server holds and that is baselined or has
    no record is recorded as uploaded (catch-up record); the notebook snapshot is
    stored, the state becomes ``done`` and the selection notice is evaluated. Never
    removes a record and never causes an upload. Blocking. Returns pages recorded.
    """
    root = Path(source_dir)
    root_key = os.path.abspath(str(root))
    entries = manifest.entries()
    elsewhere = manifest.fingerprints_elsewhere()
    uploaded: list[tuple[Path, Fingerprint]] = []
    for path, key, uuid in _folder_files(root, handler):
        if not _is_page(key, root_key) or (uuid, path.stem) not in server.pages:
            continue
        entry = entries.get(key)
        if entry is not None and not entry.is_baseline:
            continue
        try:
            st = os.stat(path)
            fp = None
            candidates = ([entry] if entry is not None else []) + list(elsewhere.get(key, ()))
            for known in candidates:
                if known.size == st.st_size and known.mtime_ns == st.st_mtime_ns:
                    fp = Fingerprint(size=known.size, mtime_ns=known.mtime_ns, sha256=known.sha256)
                    break
            fp = fp or fingerprint_file(path)
        except OSError as e:
            logger.debug(f"Skipping unreadable file during catch-up upgrade: {path}: {e}")
            continue
        if server.has_current(uuid, path.stem, fp.sha256):
            uploaded.append((path, fp))
    count = unselected_on_server_count(config, root, server.notebooks)
    notice = None
    if count and manifest.get_meta(NOTICE_KEY) is None:
        notice = NOTICE_PENDING
    manifest.apply_upgrade(uploaded=uploaded, server_notebooks=server.notebooks, state=CATCH_UP_DONE, notice=notice)
    logger.info(f"Catch-up with {manifest.api_host} completed later: {len(uploaded)} page(s) found on the server")
    return len(uploaded)


class CatchUp:
    """Decides, before each watcher scan, whether the current host is ready, and runs the catch-up.

    Owned by ``FileWatcher`` (shared by the legacy and headless modes). All
    methods except ``gate_open`` and ``retry_due`` run on the agent loop.
    """

    FIRST_RETRY_SECONDS = 5.0
    MAX_RETRY_SECONDS = 300.0
    # Network errors, 429 and 5xx for this long in a row: use the fallback (state
    # unavailable) so the app does not stay on its starting screen
    GIVE_UP_SECONDS = 600.0

    def __init__(
        self,
        config: Config,
        cloud_sync: Any,
        manifest: UploadManifest,
        clock: Callable[[], float] = time.monotonic,
        on_sign_in_required: Callable[[], None] | None = None,
    ):
        self.config = config
        self.cloud_sync = cloud_sync
        self.manifest = manifest
        self._clock = clock
        self._on_sign_in_required = on_sign_in_required
        # Host that is known to be initialised for the signed-in account
        self._ready_host: str | None = None
        # Backoff after a failed stored-pages request (or account lookup)
        self._retry_at: float | None = None
        self._delay = self.FIRST_RETRY_SECONDS
        # Why the catch-up is not done yet (for logs and /api/status)
        self.waiting_reason: str | None = None
        self.last_result: ReconcileResult | None = None
        # Start of the current run of retryable failures (None: not failing)
        self._failing_since: float | None = None
        # Hosts this instance (one per watcher start) already asked again after a fallback
        self._upgrade_tried: set[str] = set()

    # -- read from any thread ----------------------------------------------

    def gate_open(self) -> bool:
        """Whether watcher events may be queued: the current host is initialised for this account."""
        ready = self._ready_host
        return ready is not None and ready == self.manifest.api_host

    def retry_due(self) -> bool:
        """A failed catch-up is waiting and its backoff has passed."""
        return self._retry_at is not None and self._clock() >= self._retry_at

    # -- agent loop --------------------------------------------------------

    def _signed_in(self) -> bool:
        return getattr(self.cloud_sync, "authenticated", False) is True

    def _schedule_retry(self, reason: str) -> None:
        self.waiting_reason = reason
        self._retry_at = self._clock() + self._delay
        logger.info(f"Catch-up waiting ({reason}); next try in {self._delay:.0f}s")
        self._delay = min(self._delay * 2, self.MAX_RETRY_SECONDS)

    def _clear_retry(self, waiting_reason: str | None = None) -> None:
        self._retry_at = None
        self._delay = self.FIRST_RETRY_SECONDS
        self._failing_since = None
        self.waiting_reason = waiting_reason

    def _sign_in_required(self) -> None:
        # Nothing to retry until the user signs in (the reconnect rescan follows)
        self._clear_retry("sign_in")
        if self._on_sign_in_required is not None:
            try:
                self._on_sign_in_required()
            except Exception as e:  # must never break the scan
                logger.debug(f"Sign-in callback failed: {e}")

    async def _account_email(self, fetch: bool) -> str | None:
        """The signed-in account's e-mail (lower-cased); asks the cloud only if ``fetch``."""
        email = normalise_email(getattr(self.cloud_sync, "user_email", None))
        if email or not fetch:
            return email
        try:
            await self.cloud_sync.get_user_info()
        except AuthenticationRequiredError:
            self._sign_in_required()
            return None
        except Exception as e:
            logger.warning(f"Catch-up: could not look up the account ({type(e).__name__})")
            self._schedule_retry("account")
            return None
        return normalise_email(getattr(self.cloud_sync, "user_email", None))

    async def ensure_ready(self, source_dir: Path, handler: Any, reason: str = "periodic") -> bool:
        """True if the current host is initialised for the signed-in account (running the catch-up if needed).

        Never raises for cloud errors. When it returns False nothing has been
        baselined or uploaded for the host; call again on the next scan.
        """
        host = self.manifest.api_host
        manifest = self.manifest.for_host(host)
        signed_in = self._signed_in()

        initialised, stored, state = await asyncio.to_thread(
            lambda: (manifest.is_initialised(), manifest.get_meta(ACCOUNT_KEY), manifest.get_meta(CATCH_UP_KEY))
        )

        # A retry backoff applies to the scans the watcher runs by itself
        backing_off = self._retry_at is not None and not self.retry_due() and reason == "periodic"

        email = None
        if signed_in:
            # Ask the cloud only when the answer matters: binding a new host, or
            # comparing with a stored account (at most once per sign-in)
            need = not initialised or stored is not None
            email = await self._account_email(fetch=need and not backing_off)
            if email and stored and stored != email:
                removed = await asyncio.to_thread(manifest.reset_host)
                logger.info(
                    f"Another account signed in on {host}: forgot {removed} upload record(s) of the previous one"
                )
                self._ready_host = None
                initialised, stored = False, None

        if initialised:
            if email and stored is None:
                # Manifest written by an earlier version: adopt it for this account
                await asyncio.to_thread(manifest.set_account, email)
                logger.info(f"Upload records for {host} adopted for the signed-in account")
            self._ready_host = host
            if email or stored is None or not signed_in:
                self._clear_retry()  # else: keep the account lookup's backoff
            if signed_in and state == CATCH_UP_UNAVAILABLE and host not in self._upgrade_tried:
                self._upgrade_tried.add(host)
                await self._upgrade(host, manifest, source_dir, handler)
            return True

        self._ready_host = None
        if not signed_in:
            self._clear_retry("sign_in")
            return False
        if email is None or backing_off:
            if self.waiting_reason is None:
                self.waiting_reason = "account"
            return False
        return await self._reconcile(host, manifest, source_dir, handler, email)

    async def _reconcile(
        self, host: str, manifest: UploadManifest, source_dir: Path, handler: Any, email: str
    ) -> bool:
        logger.info(f"First contact with {host} for this account: asking the server what it has")
        server: ServerPages | None
        try:
            data = await self.cloud_sync.get_stored_pages()
            server = parse_stored_pages(data)
        except StoredPagesUnavailableError:
            server = None
            logger.info("Backend has no stored-pages endpoint; continuing without the server's list")
        except AuthenticationRequiredError:
            self._sign_in_required()
            return False
        except ValueError as e:
            server = None
            logger.warning(f"Catch-up: unexpected answer from the server ({e}); continuing without its list")
        except Exception as e:
            transient = not isinstance(e, CloudSyncError) or e.transient
            if not transient:
                server = None
                logger.warning(f"Catch-up request refused ({e}); continuing without the server's list")
            else:
                now = self._clock()
                if self._failing_since is None:
                    self._failing_since = now
                if now - self._failing_since < self.GIVE_UP_SECONDS:
                    logger.warning(f"Catch-up request failed ({type(e).__name__}: {e}); will retry")
                    self._schedule_retry("cloud")
                    return False
                server = None
                logger.warning(
                    f"Catch-up request failing for {self.GIVE_UP_SECONDS:.0f}s ({e}); "
                    "continuing without the server's list (asked again at the next start)"
                )

        # The user may have switched server or signed out while we waited
        if self.manifest.api_host != host or not self._signed_in():
            self._clear_retry("sign_in" if not self._signed_in() else "host_changed")
            return False

        result = await asyncio.to_thread(reconcile_folder, source_dir, handler, manifest, self.config, server, email)
        self.last_result = result
        self._ready_host = host
        self._clear_retry()
        print(
            f"✓ Caught up with rMirror Cloud: {result.uploaded} page(s) already there, "
            f"{result.left_for_upload} file(s) to upload"
        )
        return True

    async def _upgrade(self, host: str, manifest: UploadManifest, source_dir: Path, handler: Any) -> None:
        """Ask the server again for a host initialised without its list. One try; never raises."""
        try:
            server = parse_stored_pages(await self.cloud_sync.get_stored_pages())
        except AuthenticationRequiredError:
            self._sign_in_required()
            return
        except Exception as e:
            logger.info(f"Catch-up with {host} still without the server's list ({type(e).__name__})")
            return
        if self.manifest.api_host != host:
            return
        await asyncio.to_thread(upgrade_folder, source_dir, handler, manifest, self.config, server)


# ----------------------------------------------------------------------
# Read side for the local API (cheap: a few SQLite reads, no cloud calls)
# ----------------------------------------------------------------------


def catch_up_status(manifest: UploadManifest, config: Config, signed_in: bool, email: str | None) -> dict:
    """The ``catch_up`` object of ``GET /api/v2/state``.

    ``pending`` while the current host is not initialised, or a different account
    than the one the records belong to is signed in (until the watcher resets
    them). ``unselected_on_server`` is only non-zero while the selection notice is
    pending; it clears the notice by itself once the count is 0 (folder readable).
    """
    email = normalise_email(email)
    if not manifest.is_initialised():
        return {"state": CATCH_UP_PENDING, "unselected_on_server": 0}
    stored = manifest.account()
    if signed_in and email and stored and stored != email:
        return {"state": CATCH_UP_PENDING, "unselected_on_server": 0}
    state = manifest.get_meta(CATCH_UP_KEY) or CATCH_UP_NOT_NEEDED
    count = 0
    if signed_in and manifest.get_meta(NOTICE_KEY) == NOTICE_PENDING:
        source = config.remarkable.source_directory
        count = unselected_on_server_count(config, source, manifest.server_notebooks())
        # Cleared only when the count is genuinely 0: a missing or unreadable
        # folder also reads 0 and must not use the notice up
        if count == 0 and folder_state(source) == FOLDER_OK:
            manifest.set_meta(NOTICE_KEY, NOTICE_CLEARED)
    return {"state": state, "unselected_on_server": count}


def dismiss_selection_notice(manifest: UploadManifest) -> None:
    """Clear the selection notice for the current host (it is never raised again for this account)."""
    manifest.set_meta(NOTICE_KEY, NOTICE_CLEARED)
