"""
Local API v2: the interface the native Mac app (rMirror.app) uses.

The contract is ``docs/local-api.md``. Responses carry codes and numbers only,
never user-facing sentences; the app owns all wording.

Every ``/api/v2/*`` request must carry ``X-RMirror-App-Token`` when the app was
created with an app token (always in headless mode). Handlers run on werkzeug
threads and hand coroutines to the agent loop through ``shared.run_on_loop``.
"""

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from flask import Blueprint, Flask, current_app, jsonify, request
from werkzeug.exceptions import HTTPException

from app.__version__ import __version__
from app.agent_loop import AgentLoopNotRunningError, AgentLoopTimeoutError
from app.config import Config, is_loopback_host
from app.remarkable.library import (
    FOLDER_OK,
    count_page_files,
    folder_state,
    scan_documents,
    scan_library,
)
from app.sync.cloud_sync import AuthenticationRequiredError, CloudSync, CloudSyncError
from app.sync.first_run import suggest_first_sync
from app.sync.manifest import UploadManifest
from app.sync.queue import PAUSED_QUOTA, PAUSED_SIGN_IN, WAITING_OFFLINE, WAITING_RATE_LIMITED
from app.sync.quota_cache import QuotaCache, iso_utc
from app.web import shared
from app.web.shared import (
    BACKEND_TIMEOUT_SECONDS,
    ENVIRONMENT_PRESETS,
    QUICK_TIMEOUT_SECONDS,
    InitialSyncJob,
    api_base_url,
    app_token_matches,
    environment_name,
)

logger = logging.getLogger(__name__)

API_VERSION = 2
APP_TOKEN_HEADER = "X-RMirror-App-Token"
V2_PREFIX = "/api/v2"

DEFAULT_SUGGESTION_MAX = 3
MAX_SUGGESTION_MAX = 20

# Sync queue pause / wait reasons -> queue.paused_reason in /api/v2/state
_PAUSED_REASONS = {
    PAUSED_SIGN_IN: "sign_in",
    PAUSED_QUOTA: "quota",
    WAITING_RATE_LIMITED: "rate_limited",
    WAITING_OFFLINE: "offline",
}

# InitialSync stopped_reason -> outcome
_STOPPED_OUTCOMES = {"quota": "stopped_quota", "sign_in": "stopped_sign_in"}


class ApiError(Exception):
    """An error response: ``{"error": {"code": ..., "detail": ...}}``."""

    def __init__(self, code: str, status: int, detail: str = ""):
        super().__init__(detail or code)
        self.code = code
        self.status = status
        self.detail = detail


def _error_response(code: str, status: int, detail: str = ""):
    return jsonify({"error": {"code": code, "detail": detail}}), status


def _ok(status: int = 200, **extra: Any):
    return jsonify({"ok": True, **extra}), status


# ----------------------------------------------------------------------
# Accessors
# ----------------------------------------------------------------------


def _config() -> Config:
    return current_app.config["AGENT_CONFIG"]


def _cloud_sync() -> CloudSync | None:
    return current_app.config.get("CLOUD_SYNC")


def _agent() -> Any:
    return shared.get_agent(current_app)


def _signed_in() -> bool:
    cloud_sync = _cloud_sync()
    return bool(cloud_sync and cloud_sync.authenticated)


def _require_signed_in() -> CloudSync:
    cloud_sync = _cloud_sync()
    if not (cloud_sync and cloud_sync.authenticated):
        raise ApiError("not_signed_in", 401, "no valid sign-in")
    return cloud_sync


def _quota_cache() -> QuotaCache:
    agent = _agent()
    cache = getattr(agent, "quota_cache", None)
    if isinstance(cache, QuotaCache):
        return cache
    return current_app.config.setdefault("V2_QUOTA_CACHE", QuotaCache())


def _manifest() -> UploadManifest:
    manifest = current_app.config.get("V2_MANIFEST")
    if manifest is None:
        manifest = UploadManifest.for_config(_config())
        current_app.config["V2_MANIFEST"] = manifest
    return manifest


def _on_loop(coro: Any, timeout: float) -> Any:
    """Run a coroutine on the agent loop, translating loop errors into API errors."""
    try:
        return shared.run_on_loop(current_app, coro, timeout)
    except AgentLoopTimeoutError as e:
        raise ApiError("cloud_timeout", 504, str(e)) from None
    except AgentLoopNotRunningError as e:
        raise ApiError("core_not_ready", 503, str(e)) from None
    except AuthenticationRequiredError as e:
        raise ApiError("not_signed_in", 401, type(e).__name__) from None
    except (CloudSyncError, httpx.HTTPError) as e:
        raise ApiError("cloud_error", 502, _safe_detail(e)) from None


def _safe_detail(error: Exception) -> str:
    """Technical detail for the log: the error type and HTTP status, nothing else."""
    status = getattr(error, "status_code", None)
    response = getattr(error, "response", None)
    if status is None and response is not None:
        status = getattr(response, "status_code", None)
    return f"{type(error).__name__}" + (f" status={status}" if status else "")


def _json_body(required: bool = True) -> dict:
    """The request's JSON object ({} for an empty optional body)."""
    if not request.get_data(cache=True):
        if required:
            raise ApiError("invalid_request", 400, "JSON object body required")
        return {}
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiError("invalid_request", 400, "body must be a JSON object")
    return body


def _page_limit_value(value: object) -> int | None:
    """Validate a page_limit: integer >= 1 or None."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ApiError("invalid_request", 400, "page_limit must be an integer >= 1 or null")
    return value


def _uuid_list(value: object, name: str, allow_empty: bool) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise ApiError("invalid_request", 400, f"{name} must be a list of strings")
    if not value and not allow_empty:
        raise ApiError("invalid_request", 400, f"{name} must not be empty")
    # Keep order, drop duplicates
    return list(dict.fromkeys(value))


# ----------------------------------------------------------------------
# Building blocks of the responses
# ----------------------------------------------------------------------


def sync_progress(job: InitialSyncJob, pages_total: int | None = None) -> dict:
    """The initial-sync job mapped onto the v2 progress object."""
    snap = job.snapshot()
    state = snap["state"]
    counts = snap["counts"] or {}
    stats = snap["stats"] or {}
    uploaded = int(counts.get("uploaded", 0))
    failed = int(counts.get("failed", 0))

    if state == InitialSyncJob.RUNNING:
        v2_state, outcome = "running", None
    elif state == InitialSyncJob.IDLE:
        v2_state, outcome = "idle", None
    else:
        v2_state = "done"
        stopped = stats.get("stopped_reason") if isinstance(stats, dict) else None
        if state == InitialSyncJob.ERROR:
            outcome = "failed"
        elif stopped in _STOPPED_OUTCOMES:
            outcome = _STOPPED_OUTCOMES[stopped]
        elif failed == 0:
            outcome = "success"
        elif uploaded == 0:
            outcome = "failed"
        else:
            outcome = "partial"

    return {
        "state": v2_state,
        "outcome": outcome,
        "counts": {
            "uploaded": uploaded,
            "failed": failed,
            "left_out_by_page_limit": int(counts.get("skipped", 0)),
            "will_retry": int(counts.get("rate_limited", 0)),
            "notebooks_done": int(counts.get("notebooks_done", 0)),
            "notebooks_total": int(counts.get("notebooks_total", 0)),
            "pages_total": pages_total if v2_state != "idle" else None,
        },
        "started_at": iso_utc(snap["started_at"]),
        "finished_at": iso_utc(snap["finished_at"]),
    }


def _current_progress() -> dict:
    job: InitialSyncJob = current_app.config["INITIAL_SYNC_JOB"]
    started_at = job.snapshot()["started_at"]
    pages_total = None
    recorded = current_app.config.get("V2_PAGES_TOTAL")
    if recorded and started_at and recorded[0] == started_at:
        pages_total = recorded[1]
    return sync_progress(job, pages_total)


def _queue_object() -> dict:
    queue = shared.get_sync_queue(current_app)
    if queue is None:
        return {"pending": 0, "running": False, "paused_reason": None}
    stats = queue.get_stats()
    reason = stats.get("paused_reason") or getattr(queue, "waiting_reason", None)
    return {
        "pending": int(stats.get("queue_size", 0)) + int(stats.get("pending", 0)),
        "running": bool(stats.get("running")),
        "paused_reason": _PAUSED_REASONS.get(reason) if reason else None,
    }


def _upload_summary() -> str | None:
    try:
        return _manifest().last_upload_at()
    except Exception as e:  # sqlite trouble must not break the state poll
        logger.warning(f"Could not read the upload manifest: {type(e).__name__}")
        return None


def _environment() -> dict:
    url = _config().api.url
    return {"name": environment_name(url), "api_url": url}


def _scan_notebooks(source: str) -> list:
    try:
        return scan_documents(source)
    except OSError as e:
        logger.warning(f"Could not scan the reMarkable folder: {type(e).__name__}")
        return []


def _syncable_library(config: Config) -> tuple[list, list]:
    """(notebooks minus those deleted on the server with upload page counts, folders)."""
    try:
        library = scan_library(config.remarkable.source_directory)
    except OSError as e:
        logger.warning(f"Could not scan the reMarkable folder: {type(e).__name__}")
        return [], []
    excluded = set(config.sync.excluded_notebooks)
    documents = [doc for doc in library.documents if doc.uuid not in excluded]
    for doc in documents:
        doc.page_count = _upload_page_count(config, doc.uuid)
    return documents, library.folders


def _pages_to_sync(config: Config, selected_uuids: list[str] | None) -> int | None:
    """Pages this initial sync will try to upload (pages_total).

    Same rule as the sync itself (PagePlanner, which InitialSync uses): the
    notebooks in the sync, their newest pages within the page limit, minus pages
    already uploaded in this version for the current host.
    """
    from app.sync.initial_sync import PagePlanner

    try:
        return PagePlanner(config, _manifest()).count_pages_to_upload(selected_uuids)
    except Exception as e:
        logger.warning(f"Could not count pages to sync: {type(e).__name__}")
        return None


def _upload_page_count(config: Config, uuid: str) -> int:
    """Pages a sync of this notebook would upload: its .rm files, within the saved page limit."""
    count = count_page_files(config.remarkable.source_directory, uuid)
    limit = config.sync.max_pages_per_notebook
    return min(count, limit) if limit and limit > 0 else count


def _syncable_documents(config: Config) -> list:
    """Notebooks in the folder, minus those deleted on the server, with upload page counts."""
    excluded = set(config.sync.excluded_notebooks)
    documents = [doc for doc in _scan_notebooks(config.remarkable.source_directory) if doc.uuid not in excluded]
    for doc in documents:
        doc.page_count = _upload_page_count(config, doc.uuid)
    return documents


def _host() -> str:
    return _config().api._keychain_user_id


def _auth_state(signed_in: bool) -> str:
    """checking | signed_in | signed_out | offline (see docs/local-api.md)."""
    if signed_in:
        return "signed_in"
    agent = _agent()
    state = getattr(agent, "auth_state", None) if agent is not None else None
    if state in ("checking", "offline"):
        return state
    return "signed_out"


def _apply_selection(config: Config, sync_all: bool | None, selected: list[str] | None) -> None:
    """Persist a notebook selection (same semantics as the legacy selection route)."""
    if sync_all is not None:
        config.sync.sync_all_notebooks = sync_all
    if selected is not None:
        config.sync.selected_notebooks = selected


def is_v2_path(path: str) -> bool:
    return path == V2_PREFIX or path.startswith(V2_PREFIX + "/")


def check_app_token():
    """App-level before_request: every /api/v2 path needs the app token, if one is set."""
    if not is_v2_path(request.path):
        return None
    expected = current_app.config.get("APP_TOKEN")
    if not expected:
        return None
    if not app_token_matches(expected, request.headers.get(APP_TOKEN_HEADER)):
        return _error_response("bad_app_token", 401, "missing or wrong app token")
    return None


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------


def register_v2_routes(app: Flask) -> None:
    """Register /api/v2/* on the app (token check, JSON errors, endpoints)."""
    bp = Blueprint("api_v2", __name__, url_prefix=V2_PREFIX)

    # first_sync.completed for users upgrading from the menu-bar app: they saved a
    # notebook selection there. Read once at start-up, before the app changes it.
    sync_config = app.config["AGENT_CONFIG"].sync
    app.config["V2_LEGACY_SELECTION_SAVED"] = (
        not sync_config.sync_all_notebooks and bool(sync_config.selected_notebooks)
    )

    @bp.errorhandler(ApiError)
    def _api_error(error: ApiError):
        return _error_response(error.code, error.status, error.detail)

    @bp.errorhandler(Exception)
    def _unexpected(error: Exception):
        if isinstance(error, HTTPException):
            code = "invalid_request" if error.code == 400 else "internal"
            return _error_response(code, error.code or 500, error.name)
        logger.error(f"Local API v2 error on {request.path}: {type(error).__name__}", exc_info=True)
        return _error_response("internal", 500, type(error).__name__)

    # -- state -----------------------------------------------------------

    @bp.get("/state")
    def state():
        config = _config()
        cloud_sync = _cloud_sync()
        agent = _agent()
        queue = _queue_object()
        signed_in = _signed_in()

        rejected = bool(cloud_sync and getattr(cloud_sync, "sign_in_rejected", False))
        sign_in_required = queue["paused_reason"] == "sign_in" or (rejected and not signed_in)

        source = config.remarkable.source_directory
        health = shared.watcher_health(current_app)
        watcher_state = getattr(agent, "watcher_state", "idle") if agent else "idle"
        last_upload = _upload_summary()

        return jsonify({
            "api_version": API_VERSION,
            "core_version": __version__,
            "auth": {
                "state": _auth_state(signed_in),
                "signed_in": signed_in,
                "email": cloud_sync.user_email if (cloud_sync and signed_in) else None,
                "sign_in_required": sign_in_required,
            },
            "environment": {
                **_environment(),
                "dashboard_url": api_base_url(config.api.url),
            },
            "folder": {"path": source, "state": folder_state(source)},
            "watcher": {
                "state": watcher_state,
                "observer_alive": bool(health["observer_alive"]),
                "last_event_at": iso_utc(health["last_event_at"]),
                "last_rescan_at": iso_utc(health["last_rescan_at"]),
            },
            "queue": queue,
            "quota": _quota_cache().snapshot(_host()) if signed_in else None,
            "first_sync": {
                "completed": last_upload is not None
                or bool(current_app.config.get("V2_LEGACY_SELECTION_SAVED")),
            },
            "sync": _current_progress(),
            "last_upload_at": iso_utc(last_upload, naive_is_utc=True),
        })

    # -- notebooks -------------------------------------------------------

    @bp.get("/notebooks")
    def notebooks():
        config = _config()
        source = config.remarkable.source_directory
        state_value = folder_state(source)
        result = []
        folders = []
        if state_value == FOLDER_OK:
            try:
                synced = _manifest().uploaded_pages_by_notebook(source)
            except Exception as e:
                logger.warning(f"Could not read the upload manifest: {type(e).__name__}")
                synced = {}
            sync_all = config.sync.sync_all_notebooks
            selected = set(config.sync.selected_notebooks)
            # Notebooks deleted on the server are left out (deleted-notebooks -> resync)
            documents, library_folders = _syncable_library(config)
            folders = [
                {"uuid": f.uuid, "name": f.name, "parent_uuid": f.parent_uuid} for f in library_folders
            ]
            for doc in documents:
                result.append({
                    "uuid": doc.uuid,
                    "name": doc.name,
                    "folder_path": doc.folder_path,
                    "parent_uuid": doc.parent_uuid,
                    "document_type": doc.document_type,
                    "page_count": doc.page_count,
                    "last_opened_at": iso_utc(doc.last_opened_at),
                    "last_modified_at": iso_utc(doc.last_modified_at),
                    "selected": sync_all or doc.uuid in selected,
                    "synced_pages": synced.get(doc.uuid, 0),
                })
        return jsonify({
            "folder_state": state_value,
            "sync_all": config.sync.sync_all_notebooks,
            "folders": folders,
            "notebooks": result,
        })

    @bp.put("/selection")
    def selection():
        body = _json_body()
        sync_all = body.get("sync_all")
        if sync_all is not None and not isinstance(sync_all, bool):
            raise ApiError("invalid_request", 400, "sync_all must be a boolean")
        selected = None
        if "selected_notebooks" in body:
            selected = _uuid_list(body["selected_notebooks"], "selected_notebooks", allow_empty=True)
        if sync_all is None and selected is None:
            raise ApiError("invalid_request", 400, "nothing to change")
        config = _config()
        _apply_selection(config, sync_all, selected)
        config.save()
        return _ok()

    # -- first run -------------------------------------------------------

    @bp.get("/first-run/suggestion")
    def first_run_suggestion():
        raw_max = request.args.get("max", str(DEFAULT_SUGGESTION_MAX))
        try:
            max_count = int(raw_max)
        except ValueError:
            raise ApiError("invalid_request", 400, "max must be an integer") from None
        if not 1 <= max_count <= MAX_SUGGESTION_MAX:
            raise ApiError("invalid_request", 400, f"max must be 1..{MAX_SUGGESTION_MAX}")

        config = _config()
        signed_in = _signed_in()
        source = config.remarkable.source_directory
        folder_ok = folder_state(source) == FOLDER_OK

        quota = None
        if signed_in:
            cache = _quota_cache()
            host = _host()
            quota = cache.snapshot(host)
            if quota is None:
                # Not fetched yet (this endpoint is not polled, so it may ask the cloud)
                cache.store(_on_loop(_require_signed_in().get_quota_status(), QUICK_TIMEOUT_SECONDS), host=host)
                cache.note_attempt()
                quota = cache.snapshot(host)

        documents = _syncable_documents(config) if (signed_in and folder_ok) else []
        suggestion = suggest_first_sync(
            signed_in=signed_in,
            folder_ok=folder_ok,
            documents=documents,
            remaining=quota["remaining"] if quota else None,
            max_count=max_count,
        )
        return jsonify({
            "notebooks": [
                {"uuid": nb.uuid, "name": nb.name, "page_count": nb.page_count}
                for nb in suggestion.notebooks
            ],
            "total_pages": suggestion.total_pages,
            "quota": {"limit": quota["limit"], "remaining": quota["remaining"]} if quota else None,
            "reason": suggestion.reason,
        })

    # -- sync ------------------------------------------------------------

    @bp.post("/sync/start")
    def sync_start():
        body = _json_body(required=False)
        notebook_uuids = None
        if body.get("notebook_uuids") is not None:
            notebook_uuids = _uuid_list(body["notebook_uuids"], "notebook_uuids", allow_empty=False)
        page_limit = _page_limit_value(body.get("page_limit"))

        _require_signed_in()
        config = _config()
        if notebook_uuids is not None:
            known = {doc.uuid for doc in _scan_notebooks(config.remarkable.source_directory)}
            if not known.intersection(notebook_uuids):
                raise ApiError("invalid_request", 400, "none of notebook_uuids is in the folder")

        # Take the job first: concurrent requests (the server is threaded) must not
        # leave a saved selection that differs from the running sync
        job: InitialSyncJob = current_app.config["INITIAL_SYNC_JOB"]
        if not job.try_begin():
            raise ApiError("sync_already_running", 409)
        try:
            if notebook_uuids is not None or page_limit is not None:
                if notebook_uuids is not None:
                    _apply_selection(config, False, notebook_uuids)
                if page_limit is not None:
                    # Omitted or null keeps the saved limit (clear it with PUT /settings)
                    config.sync.max_pages_per_notebook = page_limit
                config.save()

            selected_uuids = None if config.sync.sync_all_notebooks else list(config.sync.selected_notebooks)
            current_app.config["V2_PAGES_TOTAL"] = (
                job.snapshot()["started_at"],
                _pages_to_sync(config, selected_uuids),
            )
            shared.launch_initial_sync(current_app, job, selected_uuids)
        except AgentLoopNotRunningError as e:
            raise ApiError("core_not_ready", 503, str(e)) from None
        except BaseException:
            if job.snapshot()["state"] == InitialSyncJob.RUNNING:
                job.reset()
            raise
        return _ok(202)

    @bp.get("/sync/progress")
    def sync_progress_route():
        return jsonify(_current_progress())

    @bp.post("/sync/resume")
    def sync_resume():
        queue = shared.get_sync_queue(current_app)
        if queue is not None:
            queue.request_resume()
        return _ok()

    # -- settings --------------------------------------------------------

    @bp.get("/settings")
    def settings_get():
        config = _config()
        return jsonify({
            "page_limit": config.sync.max_pages_per_notebook,
            "source_directory": config.remarkable.source_directory,
            "environment": _environment(),
            "environment_presets": dict(ENVIRONMENT_PRESETS),
        })

    @bp.put("/settings")
    def settings_put():
        body = _json_body()
        config = _config()
        cloud_sync = _cloud_sync()
        agent = _agent()

        # Validate everything before changing anything
        changes: dict[str, Any] = {}
        if "page_limit" in body:
            changes["page_limit"] = _page_limit_value(body["page_limit"])
        if "source_directory" in body:
            value = body["source_directory"]
            if not isinstance(value, str) or not value.strip():
                raise ApiError("invalid_request", 400, "source_directory must be a non-empty string")
            changes["source_directory"] = str(Path(value.strip()).expanduser().resolve())
        if "environment" in body:
            env = body["environment"]
            if not isinstance(env, dict):
                raise ApiError("invalid_request", 400, "environment must be an object")
            name = env.get("name")
            if name in ENVIRONMENT_PRESETS:
                new_url = ENVIRONMENT_PRESETS[name]
            elif name == "custom":
                new_url = env.get("api_url")
                if not isinstance(new_url, str):
                    raise ApiError("invalid_request", 400, "custom environment needs an api_url")
                new_url = new_url.strip().rstrip("/")
                parts = urlparse(new_url)
                # Plain http only to this machine: the sign-in token must not travel in clear
                if not parts.hostname or not (
                    parts.scheme == "https" or (parts.scheme == "http" and is_loopback_host(parts.hostname))
                ):
                    raise ApiError("invalid_request", 400, "api_url must be https (or http to loopback)")
            else:
                raise ApiError("invalid_request", 400, "unknown environment")
            changes["api_url"] = new_url

        environment_changed = "api_url" in changes and changes["api_url"] != config.api.url
        job: InitialSyncJob = current_app.config["INITIAL_SYNC_JOB"]
        if environment_changed and job.snapshot()["state"] == InitialSyncJob.RUNNING:
            raise ApiError("sync_already_running", 409, "environment cannot change during a sync")

        if "page_limit" in changes:
            config.sync.max_pages_per_notebook = changes["page_limit"]

        folder_changed = (
            "source_directory" in changes
            and changes["source_directory"] != config.remarkable.source_directory
        )
        if folder_changed and not hasattr(agent, "change_source_directory"):
            config.remarkable.source_directory = changes["source_directory"]

        if environment_changed:
            # Same as the legacy environment switch: per-host sign-in and manifest
            config.api.url = changes["api_url"]
            config.api._token = None
            if cloud_sync:
                cloud_sync.authenticated = False
                cloud_sync.user_email = None
                cloud_sync.user_id = None
            _quota_cache().clear()
            current_app.config.pop("V2_MANIFEST", None)

        config.save()

        if folder_changed and hasattr(agent, "change_source_directory"):
            # Stops the watcher, records the files already in the new folder as
            # baseline (never uploaded wholesale) and watches the new folder
            _on_loop(agent.change_source_directory(changes["source_directory"]), BACKEND_TIMEOUT_SECONDS)

        has_token = bool(config.api.token)
        if environment_changed and has_token and agent is not None:
            # A sign-in stored for that environment: check it in the background
            try:
                shared.agent_loop(current_app).submit(agent.reauthenticate())
            except AgentLoopNotRunningError:
                pass

        return _ok(needs_sign_in=not has_token)

    # -- account ---------------------------------------------------------

    @bp.post("/auth/begin")
    def auth_begin():
        """A single-use URL that opens the browser sign-in (/auth/bridge) for this core."""
        tickets = current_app.config.get("BRIDGE_TICKETS")
        if tickets is None:
            raise ApiError("core_not_ready", 503, "sign-in routes not registered")
        ticket = tickets.issue()
        port = _config().web.port
        return jsonify({"url": f"http://127.0.0.1:{port}/auth/bridge?ticket={ticket}"})

    @bp.post("/auth/sign-out")
    def sign_out():
        cloud_sync = _cloud_sync()
        if cloud_sync:
            cloud_sync.logout()
        _quota_cache().clear()
        agent = _agent()
        if agent is not None and hasattr(agent, "auth_state"):
            agent.auth_state = "signed_out"
        if agent is not None and hasattr(agent, "stop_file_watcher"):
            _on_loop(agent.stop_file_watcher(), BACKEND_TIMEOUT_SECONDS)
        return _ok()

    # -- deleted notebooks -----------------------------------------------

    @bp.get("/deleted-notebooks")
    def deleted_notebooks():
        if not _signed_in():
            return jsonify({"deleted_notebooks": []})
        items = _on_loop(_require_signed_in().get_deleted_notebooks(), QUICK_TIMEOUT_SECONDS)
        result = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            uuid = item.get("notebook_uuid") or item.get("uuid")
            if not uuid:
                continue
            result.append({
                "uuid": uuid,
                "name": item.get("visible_name") or item.get("name") or "",
                "deleted_at": iso_utc(item.get("deleted_at"), naive_is_utc=True),
            })
        return jsonify({"deleted_notebooks": result})

    @bp.post("/deleted-notebooks/<uuid>")
    def deleted_notebook_action(uuid: str):
        body = _json_body()
        action = body.get("action")
        if action not in ("resync", "dismiss"):
            raise ApiError("invalid_request", 400, "action must be resync or dismiss")
        cloud_sync = _require_signed_in()
        if action == "resync":
            shared.prepare_resync(current_app, uuid)
        _on_loop(cloud_sync.acknowledge_deleted_notebook(uuid, action), BACKEND_TIMEOUT_SECONDS)
        if action == "resync":
            # Upload it now rather than at the next periodic rescan
            shared.request_rescan(current_app, "resync")
        return _ok()

    # -- updates ---------------------------------------------------------

    @bp.get("/update-check")
    def update_check():
        from app.updater import check_for_updates

        info = _on_loop(check_for_updates(), QUICK_TIMEOUT_SECONDS)
        if info.error:
            raise ApiError("cloud_error", 502, "update check failed")
        return jsonify({
            "has_update": info.has_update,
            "current_version": info.current_version,
            "latest_version": info.latest_version,
            "download_url": info.download_url,
        })

    app.register_blueprint(bp)

    # Unknown /api/v2 paths and wrong methods answer in JSON too (other paths unchanged)
    def _v2_http_error(error: HTTPException):
        if not is_v2_path(request.path):
            return error
        code = {400: "invalid_request", 404: "invalid_request", 405: "invalid_request"}.get(
            error.code or 500, "internal"
        )
        return _error_response(code, error.code or 500, error.name)

    app.register_error_handler(404, _v2_http_error)
    app.register_error_handler(405, _v2_http_error)

