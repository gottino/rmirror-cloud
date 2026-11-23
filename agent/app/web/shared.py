"""
State and helpers shared by the legacy web routes (``routes.py``) and the local
API v2 (``routes_v2.py``).

Everything per app lives in ``app.config``: the agent, its loop, the CloudSync
client, the initial-sync job (``INITIAL_SYNC_JOB``) and the one-time sign-in
states (``AUTH_STATES``), so both route sets see the same state.
"""

import asyncio
import hmac
import logging
import secrets
import threading
import time
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any

from flask import Flask

from app.agent_loop import AgentLoopNotRunningError, AgentLoopTimeoutError

logger = logging.getLogger(__name__)

# How long a request waits for its coroutine on the agent loop. Routes run on
# werkzeug threads and hand coroutines to the agent's single event loop (where
# CloudSync and its HTTP client live) instead of running their own loops.
BACKEND_TIMEOUT_SECONDS = 30.0  # calls that may re-authenticate or write
QUICK_TIMEOUT_SECONDS = 15.0  # read-only lookups the UI polls

# Errors from handing work to the agent loop
LOOP_ERRORS = (AgentLoopTimeoutError, AgentLoopNotRunningError)

ENVIRONMENT_PRESETS = {
    "production": "https://rmirror.io/api/v1",
    "staging": "https://staging.rmirror.io/api/v1",
}


def app_token_matches(expected: str | None, given: str | None) -> bool:
    """Constant-time comparison of the X-RMirror-App-Token header."""
    if not expected or given is None:
        return False
    return hmac.compare_digest(expected.encode(), given.encode())


def environment_name(api_url: str) -> str:
    """production, staging or custom."""
    for name, url in ENVIRONMENT_PRESETS.items():
        if api_url == url:
            return name
    return "custom"


def api_base_url(api_url: str) -> str:
    """The site root of an API URL (strip the /api/v1 or /v1 suffix)."""
    for suffix in ("/api/v1", "/api/v1/", "/v1", "/v1/"):
        if api_url.endswith(suffix):
            return api_url[: -len(suffix)]
    return api_url


# Headless sign-in: /auth/bridge only starts a sign-in for a ticket the app got
# from POST /api/v2/auth/begin (which needs the app token)
BRIDGE_TICKET_TTL_SECONDS = 600
MAX_BRIDGE_TICKETS = 5


class BridgeTicketStore:
    """Single-use, short-lived tickets that open /auth/bridge in headless mode."""

    def __init__(self, ttl_seconds: float = BRIDGE_TICKET_TTL_SECONDS, max_pending: int = MAX_BRIDGE_TICKETS):
        self._ttl = ttl_seconds
        self._max = max_pending
        self._tickets: dict[str, float] = {}
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        for value, expires_at in list(self._tickets.items()):
            if expires_at <= now:
                del self._tickets[value]

    def issue(self) -> str:
        """A new ticket; the oldest outstanding one is dropped when the store is full."""
        value = secrets.token_urlsafe(32)
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            while len(self._tickets) >= self._max:
                del self._tickets[min(self._tickets, key=self._tickets.get)]
            self._tickets[value] = now + self._ttl
        return value

    def consume(self, value: str | None) -> bool:
        """True if value is an outstanding unexpired ticket; it is used up either way."""
        if not value:
            return False
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            match = None
            for stored in self._tickets:
                if hmac.compare_digest(stored.encode(), value.encode()):
                    match = stored
            if match is None:
                return False
            del self._tickets[match]
            return True


class InitialSyncJob:
    """State of the initial sync, which runs as a task on the agent loop."""

    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = self.IDLE
        self._stats: dict | None = None
        self._message: str | None = None
        self._started_at: str | None = None
        self._finished_at: str | None = None
        self._counts: dict | None = None

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def try_begin(self) -> bool:
        """Mark the job running; False if it already is."""
        with self._lock:
            if self._state == self.RUNNING:
                return False
            self._state = self.RUNNING
            self._stats = None
            self._counts = None
            self._message = None
            self._started_at = self._now()
            self._finished_at = None
            return True

    def reset(self) -> None:
        """Back to idle (the job could not be started)."""
        with self._lock:
            self._state = self.IDLE
            self._started_at = None

    def update_progress(self, counts: dict) -> None:
        """Live page counts from the running sync (called on the agent loop)."""
        with self._lock:
            if self._state == self.RUNNING:
                self._counts = dict(counts)

    def finish(self, stats: dict) -> None:
        with self._lock:
            self._state = self.DONE
            self._stats = stats
            # Final counts come from the returned stats, which are authoritative
            self._counts = {
                **(self._counts or {}),
                "uploaded": stats.get("pages", 0),
                "failed": stats.get("failed", 0),
                "skipped": stats.get("skipped", 0),
                "rate_limited": stats.get("rate_limited", 0),
            }
            self._finished_at = self._now()

    def fail(self, message: str) -> None:
        with self._lock:
            self._state = self.ERROR
            self._message = message
            self._finished_at = self._now()

    def _outcome(self) -> str | None:
        """For a finished run: success, partial (some pages not uploaded) or failed (none uploaded)."""
        if self._state != self.DONE or self._counts is None:
            return None
        missed = self._counts["failed"] + self._counts["rate_limited"]
        if missed == 0:
            return "success"
        return "failed" if self._counts["uploaded"] == 0 else "partial"

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "state": self._state,
                "stats": self._stats,
                "counts": dict(self._counts) if self._counts is not None else None,
                "outcome": self._outcome(),
                "message": self._message,
                "started_at": self._started_at,
                "finished_at": self._finished_at,
            }


async def run_initial_sync(
    job: InitialSyncJob, initial_sync: Any, selected_uuids: list[str] | None, agent: Any = None
) -> None:
    """Run the initial sync on the agent loop and record the outcome in job."""
    try:
        stats = await initial_sync.run(selected_uuids)
    except asyncio.CancelledError:
        job.fail("Initial sync was cancelled (agent stopping)")
        raise
    except Exception as e:
        logger.error(f"Initial sync failed: {e}", exc_info=True)
        job.fail(str(e))
    else:
        job.finish(stats)
    finally:
        # Uploads change the quota (headless agents keep a cache of it)
        if agent is not None and getattr(agent, "headless", False):
            agent.quota_cache.mark_stale()


class SyncAlreadyRunningError(Exception):
    """The initial sync is already running."""


def start_initial_sync(app: Flask, selected_uuids: list[str] | None) -> InitialSyncJob:
    """Begin the initial sync job and hand it to the agent loop.

    Raises SyncAlreadyRunningError, AgentLoopNotRunningError (job reset to idle) or
    any error from setting it up (job marked failed). The caller checks sign-in.
    """
    job: InitialSyncJob = app.config["INITIAL_SYNC_JOB"]
    if not job.try_begin():
        raise SyncAlreadyRunningError()
    return launch_initial_sync(app, job, selected_uuids)


def launch_initial_sync(app: Flask, job: InitialSyncJob, selected_uuids: list[str] | None) -> InitialSyncJob:
    """Hand an already begun job (``job.try_begin()`` returned True) to the agent loop.

    On AgentLoopNotRunningError the job goes back to idle; on any other setup error
    it is marked failed. Both are re-raised.
    """
    from app.sync.initial_sync import InitialSync

    try:
        initial_sync = InitialSync(
            app.config["AGENT_CONFIG"], app.config["CLOUD_SYNC"], on_progress=job.update_progress
        )
        # Runs as a task on the agent loop; the UI polls the job's state
        agent_loop(app).submit(run_initial_sync(job, initial_sync, selected_uuids, get_agent(app)))
    except AgentLoopNotRunningError:
        job.reset()
        raise
    except Exception as e:
        job.fail(str(e))
        raise
    return job


def prepare_resync(app: Flask, notebook_uuid: str) -> int:
    """"Sync again" for a notebook deleted on the server (before acknowledging it).

    Takes it off the excluded list, makes sure it is selected (unless everything
    is synced), and forgets its manifest entries for the current host: otherwise
    its pages would still count as uploaded and nothing would ever send them again.
    Returns the number of manifest entries removed.
    """
    from app.sync.manifest import UploadManifest

    config = app.config["AGENT_CONFIG"]
    if notebook_uuid in config.sync.excluded_notebooks:
        config.sync.excluded_notebooks.remove(notebook_uuid)
    if not config.sync.sync_all_notebooks and notebook_uuid not in config.sync.selected_notebooks:
        config.sync.selected_notebooks.append(notebook_uuid)
    config.save()
    manifest = app.config.get("V2_MANIFEST") or UploadManifest.for_config(config)
    removed = manifest.forget_notebook(config.remarkable.source_directory, notebook_uuid)
    logger.info(f"Notebook {notebook_uuid[:8]} set to sync again ({removed} manifest entries cleared)")
    return removed


def request_rescan(app: Flask, reason: str) -> bool:
    """Ask the running watcher to rescan now (no wait). False if no watcher is running."""
    agent = get_agent(app)
    file_watcher = getattr(agent, "file_watcher", None) if agent else None
    if file_watcher is None or not getattr(file_watcher, "running", False):
        return False
    try:
        agent_loop(app).submit(file_watcher.rescan(reason=reason))
    except AgentLoopNotRunningError:
        return False
    return True


def get_agent(app: Flask) -> Any:
    return app.config.get("AGENT")


def get_sync_queue(app: Flask) -> Any:
    """The running watcher's sync queue, if there is one."""
    agent = get_agent(app)
    file_watcher = getattr(agent, "file_watcher", None) if agent else None
    return getattr(file_watcher, "sync_queue", None)


def watcher_health(app: Flask) -> dict:
    """Observer and rescan state of the running watcher (empty values if none)."""
    agent = get_agent(app)
    file_watcher = getattr(agent, "file_watcher", None) if agent else None
    get_health = getattr(file_watcher, "get_health", None)
    health = get_health() if callable(get_health) else None
    if not isinstance(health, dict):
        health = {}
    return {
        "observer_alive": health.get("observer_alive", False),
        "last_event_at": health.get("last_event_at"),
        "last_rescan_at": health.get("last_rescan_at"),
        "last_rescan_reason": health.get("last_rescan_reason"),
        "last_rescan_result": health.get("last_rescan_result"),
        "observer_restarts": health.get("observer_restarts", 0),
    }


def agent_loop(app: Flask) -> Any:
    loop = app.config.get("AGENT_LOOP")
    if loop is None:
        raise AgentLoopNotRunningError("No agent event loop configured")
    return loop


def run_on_loop(app: Flask, coro: Coroutine[Any, Any, Any], timeout: float) -> Any:
    """Run coro on the agent loop and wait for it (raises one of LOOP_ERRORS)."""
    try:
        loop = agent_loop(app)
    except AgentLoopNotRunningError:
        coro.close()
        raise
    return loop.run(coro, timeout)
