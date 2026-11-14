"""
Flask routes for rMirror Agent web UI.
"""

import asyncio
import hmac
import logging
import secrets
import threading
import time
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import httpx
from flask import Flask, jsonify, redirect, render_template, request

from app.__version__ import __version__
from app.agent_loop import AgentLoopNotRunningError, AgentLoopTimeoutError
from app.config import Config
from app.sync.cloud_sync import CloudSync, CloudSyncError
from app.sync.queue import PAUSED_SIGN_IN

logger = logging.getLogger(__name__)

# How long a request waits for its coroutine on the agent loop. Routes run on
# werkzeug threads and hand coroutines to the agent's single event loop (where
# CloudSync and its HTTP client live) instead of running their own loops.
BACKEND_TIMEOUT_SECONDS = 30.0  # calls that may re-authenticate or write
QUICK_TIMEOUT_SECONDS = 15.0  # read-only lookups the UI polls

# Errors from handing work to the agent loop
_LOOP_ERRORS = (AgentLoopTimeoutError, AgentLoopNotRunningError)


def _loop_error_body(error: Exception) -> tuple[dict, int]:
    """JSON body and status for a request whose work could not finish on the agent loop."""
    if isinstance(error, AgentLoopTimeoutError):
        return {
            "success": False,
            "error": "timeout",
            "message": "rMirror Cloud did not answer in time. Please try again.",
        }, 504
    return {
        "success": False,
        "error": "agent_not_ready",
        "message": "The agent is not running (starting up or shutting down). Please try again.",
    }, 503


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
            self._message = None
            self._started_at = self._now()
            self._finished_at = None
            return True

    def reset(self) -> None:
        """Back to idle (the job could not be started)."""
        with self._lock:
            self._state = self.IDLE
            self._started_at = None

    def finish(self, stats: dict) -> None:
        with self._lock:
            self._state = self.DONE
            self._stats = stats
            self._finished_at = self._now()

    def fail(self, message: str) -> None:
        with self._lock:
            self._state = self.ERROR
            self._message = message
            self._finished_at = self._now()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "state": self._state,
                "stats": self._stats,
                "message": self._message,
                "started_at": self._started_at,
                "finished_at": self._finished_at,
            }


async def _run_initial_sync(job: InitialSyncJob, initial_sync: Any, selected_uuids: list[str] | None) -> None:
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


async def register_agent_with_backend(
    cloud_sync: CloudSync,
    version: str,
    platform: str,
    hostname: str
) -> None:
    """
    Register agent with backend after successful authentication.

    Args:
        cloud_sync: CloudSync instance
        version: Agent version
        platform: Platform (e.g., "Darwin" for macOS)
        hostname: Machine hostname
    """
    client = cloud_sync.ensure_client()

    try:
        response = await client.post(
            f"{cloud_sync.config.api.url}/agents/register",
            timeout=30.0,
            headers={"Authorization": f"Bearer {cloud_sync.config.api.token}"},
            json={
                "version": version,
                "platform": platform,
                "hostname": hostname,
            },
        )
        response.raise_for_status()
        print("✓ Agent registered with backend")
    except Exception as e:
        print(f"⚠ Failed to register agent with backend: {e}")
        raise


# One-time sign-in state: issued by /auth/bridge, required by /auth/callback.
AUTH_STATE_TTL_SECONDS = 600
_MAX_PENDING_AUTH_STATES = 20


class AuthStateStore:
    """In-memory store of one-time sign-in states with a short expiry."""

    def __init__(self, ttl_seconds: float = AUTH_STATE_TTL_SECONDS):
        self._ttl = ttl_seconds
        self._states: dict[str, float] = {}
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        for value, expires_at in list(self._states.items()):
            if expires_at <= now:
                del self._states[value]

    def issue(self) -> str:
        """Create and remember a new random state."""
        value = secrets.token_urlsafe(32)
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            # Keep the store bounded; drop the oldest pending states first
            while len(self._states) >= _MAX_PENDING_AUTH_STATES:
                oldest = min(self._states, key=self._states.get)
                del self._states[oldest]
            self._states[value] = now + self._ttl
        return value

    def consume(self, value: str | None) -> bool:
        """Return True if value matches a pending unexpired state; it is removed either way."""
        if not value:
            return False
        now = time.monotonic()
        with self._lock:
            self._prune(now)
            match = None
            for stored in self._states:
                if hmac.compare_digest(stored.encode(), value.encode()):
                    match = stored
            if match is None:
                return False
            del self._states[match]
            return True


async def verify_agent_token(cloud_sync: CloudSync, token: str) -> bool:
    """Check a candidate token against the backend before it is stored."""
    client = cloud_sync.ensure_client()

    try:
        response = await client.get(
            f"{cloud_sync.config.api.url}/sync/stats",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )
    except httpx.HTTPError:
        return False
    return response.status_code == 200


def register_routes(app: Flask) -> None:
    """Register all web UI routes."""

    def _sync_queue():
        """The running watcher's sync queue, if there is one."""
        agent = app.config.get("AGENT")
        file_watcher = getattr(agent, "file_watcher", None) if agent else None
        return getattr(file_watcher, "sync_queue", None)

    auth_states = AuthStateStore()
    app.config["AUTH_STATES"] = auth_states

    initial_sync_job = InitialSyncJob()
    app.config["INITIAL_SYNC_JOB"] = initial_sync_job

    def _agent_loop():
        agent_loop = app.config.get("AGENT_LOOP")
        if agent_loop is None:
            raise AgentLoopNotRunningError("No agent event loop configured")
        return agent_loop

    def _on_loop(coro: Coroutine[Any, Any, Any], timeout: float) -> Any:
        """Run coro on the agent loop and wait for it (raises one of _LOOP_ERRORS)."""
        try:
            agent_loop = _agent_loop()
        except AgentLoopNotRunningError:
            coro.close()
            raise
        return agent_loop.run(coro, timeout)

    def _loop_error(error: Exception, **extra: Any):
        body, status = _loop_error_body(error)
        return jsonify({**body, **extra}), status

    @app.route("/")
    def index():
        """Main dashboard page."""
        config: Config = app.config["AGENT_CONFIG"]
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]
        agent = app.config.get("AGENT")
        remarkable_folder_missing = agent.remarkable_folder_missing if agent else not Path(config.remarkable.source_directory).exists()
        return render_template(
            "index.html",
            config=config,
            api_url=config.api.url,
            email=config.api.email,
            remarkable_dir=config.remarkable.source_directory,
            auto_sync=config.sync.auto_sync,
            max_pages_per_notebook=config.sync.max_pages_per_notebook,
            use_clerk_auth=config.api.use_clerk_auth,
            authenticated=cloud_sync.authenticated if cloud_sync else False,
            remarkable_folder_missing=remarkable_folder_missing,
            dev_mode=config.dev.dev_mode,
        )

    @app.route("/api/status")
    def api_status():
        """Get agent status."""
        config: Config = app.config["AGENT_CONFIG"]
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]
        sync_queue = _sync_queue()
        queue_stats = sync_queue.get_stats() if sync_queue else None
        paused_reason = queue_stats["paused_reason"] if queue_stats else None

        return jsonify(
            {
                "agent": {
                    "running": True,
                    "version": "0.1.0",
                },
                "authentication": {
                    "authenticated": cloud_sync.authenticated if cloud_sync else False,
                    "email": config.api.email,
                    "sign_in_required": paused_reason == PAUSED_SIGN_IN,
                },
                "watching": {
                    "enabled": config.remarkable.watch_enabled,
                    "directory": config.remarkable.source_directory,
                    "exists": Path(config.remarkable.source_directory).exists(),
                },
                "sync": {
                    "auto_sync": config.sync.auto_sync,
                    "batch_size": config.sync.batch_size,
                    "sync_interval": config.sync.sync_interval,
                    "paused_reason": paused_reason,
                    "queue": queue_stats,
                },
            }
        )

    @app.route("/api/config", methods=["GET", "POST"])
    def api_config():
        """Get or update configuration."""
        config: Config = app.config["AGENT_CONFIG"]

        if request.method == "GET":
            return jsonify(
                {
                    "api": {
                        "url": config.api.url,
                        "email": config.api.email,
                    },
                    "remarkable": {
                        "source_directory": config.remarkable.source_directory,
                        "watch_enabled": config.remarkable.watch_enabled,
                    },
                    "sync": {
                        "auto_sync": config.sync.auto_sync,
                        "batch_size": config.sync.batch_size,
                        "sync_interval": config.sync.sync_interval,
                    },
                }
            )

        # POST - Update configuration
        data = request.json

        # Update API config
        if "api" in data:
            if "url" in data["api"]:
                config.api.url = data["api"]["url"]
            if "email" in data["api"]:
                config.api.email = data["api"]["email"]
            if "password" in data["api"]:
                config.api.password = data["api"]["password"]

        # Update reMarkable config
        if "remarkable" in data:
            if "source_directory" in data["remarkable"]:
                config.remarkable.source_directory = data["remarkable"]["source_directory"]
            if "watch_enabled" in data["remarkable"]:
                config.remarkable.watch_enabled = data["remarkable"]["watch_enabled"]

        # Update sync config
        if "sync" in data:
            if "auto_sync" in data["sync"]:
                config.sync.auto_sync = data["sync"]["auto_sync"]
            if "batch_size" in data["sync"]:
                config.sync.batch_size = data["sync"]["batch_size"]
            if "sync_interval" in data["sync"]:
                config.sync.sync_interval = data["sync"]["sync_interval"]
            if "max_pages_per_notebook" in data["sync"]:
                config.sync.max_pages_per_notebook = data["sync"]["max_pages_per_notebook"]

        # Save configuration
        config.save()

        # Re-check folder state and update agent
        agent = app.config.get("AGENT")
        if agent:
            new_path = Path(config.remarkable.source_directory)
            agent.remarkable_folder_missing = not new_path.exists()
            if new_path.exists() and not agent.file_watcher and config.remarkable.watch_enabled:
                cloud_sync: CloudSync = app.config["CLOUD_SYNC"]
                if cloud_sync and cloud_sync.authenticated:
                    agent.start_file_watcher_sync()

        return jsonify({"success": True, "message": "Configuration updated"})

    @app.route("/api/sync/status")
    def api_sync_status():
        """Get sync status from backend."""
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]

        try:
            status = _on_loop(cloud_sync.get_sync_status(), BACKEND_TIMEOUT_SECONDS)
            return jsonify(status)
        except _LOOP_ERRORS as e:
            return _loop_error(e)
        except CloudSyncError as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/sync/trigger", methods=["POST"])
    def api_sync_trigger():
        """Trigger immediate sync."""
        # TODO: Implement manual sync trigger
        # A paused queue (e.g. quota exceeded) re-checks now instead of waiting
        sync_queue = _sync_queue()
        if sync_queue:
            sync_queue.request_resume()
        return jsonify({"success": True, "message": "Manual sync triggered"})

    @app.route("/api/sync/initial", methods=["POST"])
    def api_sync_initial():
        """
        Trigger initial sync of all notebooks.

        This uploads all pages and .content files for selected notebooks.
        Useful for first-time setup or catching up after being offline.
        """
        from app.sync.initial_sync import InitialSync

        config: Config = app.config["AGENT_CONFIG"]
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]

        if not cloud_sync or not cloud_sync.authenticated:
            return jsonify({"success": False, "message": "Not authenticated"}), 401

        if not initial_sync_job.try_begin():
            return jsonify({
                "success": False,
                "message": "Initial sync is already running",
                **initial_sync_job.snapshot(),
            }), 409

        try:
            # Get selected notebooks
            selected_uuids = None
            if not config.sync.sync_all_notebooks:
                selected_uuids = config.sync.selected_notebooks

            initial_sync = InitialSync(config, cloud_sync)

            # Runs as a task on the agent loop; the UI polls /api/sync/initial/status
            _agent_loop().submit(_run_initial_sync(initial_sync_job, initial_sync, selected_uuids))
        except AgentLoopNotRunningError as e:
            initial_sync_job.reset()
            return _loop_error(e)
        except Exception as e:
            app.logger.error(f"Initial sync failed to start: {e}", exc_info=True)
            initial_sync_job.fail(str(e))
            return jsonify({"success": False, "message": str(e)}), 500

        return jsonify({
            "success": True,
            "message": "Initial sync started",
            **initial_sync_job.snapshot(),
        }), 202

    @app.route("/api/sync/initial/status")
    def api_sync_initial_status():
        """State of the initial sync: idle, running, done (with stats) or error (with message)."""
        return jsonify(initial_sync_job.snapshot())

    @app.route("/api/test-connection", methods=["POST"])
    def api_test_connection():
        """Test connection to backend API."""
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]

        try:
            _on_loop(cloud_sync.authenticate(), BACKEND_TIMEOUT_SECONDS)
            return jsonify(
                {
                    "success": True,
                    "message": f"Successfully authenticated as {cloud_sync.config.api.email}",
                }
            )
        except _LOOP_ERRORS as e:
            return _loop_error(e)
        except CloudSyncError as e:
            return jsonify({"success": False, "message": str(e)}), 401

    @app.route("/auth/bridge")
    def auth_bridge():
        """Serve the Clerk auth bridge page with dynamically injected config.

        Fetches the Clerk publishable key from the backend so the agent
        doesn't need any hardcoded keys. Works with any Clerk environment
        (production, staging, dev) based on the configured API URL.
        """
        config: Config = app.config["AGENT_CONFIG"]

        # Derive base URL from API URL (strip /api/v1 suffix)
        api_base = config.api.url
        for suffix in ("/api/v1", "/api/v1/", "/v1", "/v1/"):
            if api_base.endswith(suffix):
                api_base = api_base[: -len(suffix)]
                break

        # Fetch Clerk publishable key from backend
        clerk_key = None
        try:
            resp = httpx.get(f"{api_base}/v1/agents/clerk-config", timeout=10)
            if resp.status_code == 200:
                clerk_key = resp.json().get("clerk_publishable_key")
        except Exception as e:
            print(f"Failed to fetch Clerk config from backend: {e}")

        if not clerk_key:
            return (
                "<h2>Could not fetch Clerk config from backend</h2>"
                f"<p>Is the API URL correct? Currently: <code>{config.api.url}</code></p>"
                "<p><a href='/'>Back to agent</a></p>"
            ), 502

        # One-time state that /auth/callback must receive back
        state = auth_states.issue()

        # Production Clerk keys only work from their registered domain,
        # so redirect to the external bridge page hosted on that domain.
        if clerk_key.startswith("pk_live_"):
            callback = (
                f"http://localhost:{config.web.port}/auth/callback?"
                + urlencode({"state": state})
            )
            return redirect(f"{api_base}/agent?callback={quote(callback, safe='')}")

        # Dev/test keys work from localhost — serve the local bridge
        return render_template(
            "auth_bridge.html",
            clerk_publishable_key=clerk_key,
            api_url=f"{api_base}/v1",
            state=state,
        )

    @app.route("/auth/callback")
    def auth_callback():
        """
        Handle Clerk OAuth callback redirect with JWT token in URL.

        Expected query parameters:
        ?state=<one-time state from /auth/bridge>&token=<agent token>
        """
        import platform

        config: Config = app.config["AGENT_CONFIG"]

        try:
            # The state is single-use: consume it before looking at the token
            if not auth_states.consume(request.args.get("state")):
                return render_template(
                    "auth_result.html",
                    success=False,
                    message="Sign-in request expired or not started from this agent. Please sign in again.",
                ), 400

            token = request.args.get("token")
            if not token:
                return render_template("auth_result.html", success=False, message="Missing authentication token")

            # Verify the token with the backend before replacing the stored one
            cloud_sync: CloudSync = app.config["CLOUD_SYNC"]
            try:
                token_ok = _on_loop(verify_agent_token(cloud_sync, token), BACKEND_TIMEOUT_SECONDS)
            except _LOOP_ERRORS as e:
                body, status = _loop_error_body(e)
                return render_template("auth_result.html", success=False, message=body["message"]), status
            if not token_ok:
                return render_template(
                    "auth_result.html",
                    success=False,
                    message="Could not verify the sign-in token with rMirror Cloud. Please sign in again.",
                ), 401

            # Store the JWT token in config (will be saved to keychain)
            config.api.token = token
            config.api.use_clerk_auth = True

            # Save configuration
            config.save()

            # Mark cloud sync as authenticated
            cloud_sync.authenticated = True

            # Register agent with backend
            try:
                # Get agent info
                agent_version = __version__
                agent_platform = platform.system()
                agent_hostname = platform.node()

                # Register with backend
                _on_loop(
                    register_agent_with_backend(
                        cloud_sync,
                        agent_version,
                        agent_platform,
                        agent_hostname
                    ),
                    BACKEND_TIMEOUT_SECONDS,
                )
            except Exception as e:
                # Log error but don't fail authentication
                app.logger.error(f"Failed to register agent: {e}")

            # Start file watcher now that we're authenticated
            agent = app.config.get("AGENT")
            if agent and config.remarkable.watch_enabled:
                try:
                    agent.start_file_watcher_sync()
                    app.logger.info("File watcher started after authentication")
                except Exception as e:
                    app.logger.error(f"Failed to start file watcher: {e}")

            # Redirect to dashboard - the setup wizard will detect agent connection
            dashboard_url = config.api.url.replace("/api/v1", "").replace("/api", "")
            if not dashboard_url or "localhost:8000" in dashboard_url:
                dashboard_url = "https://rmirror.io"
            return redirect(f"{dashboard_url}/dashboard")
        except Exception as e:
            return render_template("auth_result.html", success=False, message=str(e))

    @app.route("/api/auth/status")
    def api_auth_status():
        """Get current authentication status."""
        config: Config = app.config["AGENT_CONFIG"]
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]

        return jsonify({
            "authenticated": cloud_sync.authenticated if cloud_sync else False,
            "use_clerk_auth": config.api.use_clerk_auth,
            "has_token": bool(config.api.token),
            "clerk_frontend_api": config.api.clerk_frontend_api,
            "email": cloud_sync.user_email if cloud_sync else None,
        })

    @app.route("/api/auth/me")
    def api_auth_me():
        """Get current user info from backend."""
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]

        if not cloud_sync or not cloud_sync.authenticated:
            return jsonify({"error": "Not authenticated"}), 401

        try:
            user_data = _on_loop(cloud_sync.get_user_info(), QUICK_TIMEOUT_SECONDS)
            return jsonify(user_data)
        except _LOOP_ERRORS as e:
            return _loop_error(e)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/auth/logout", methods=["POST"])
    def api_auth_logout():
        """Sign out and clear stored token."""
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]

        if cloud_sync:
            cloud_sync.logout()

        return jsonify({"success": True, "message": "Signed out successfully"})

    environment_presets = {
        "production": "https://rmirror.io/api/v1",
        "staging": "https://staging.rmirror.io/api/v1",
    }

    @app.route("/api/auth/environment", methods=["GET", "POST"])
    def api_auth_environment():
        """Get or switch the backend environment."""
        config: Config = app.config["AGENT_CONFIG"]
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]

        if request.method == "GET":
            # Determine current environment from URL
            current_env = "custom"
            for env_name, env_url in environment_presets.items():
                if config.api.url == env_url:
                    current_env = env_name
                    break

            return jsonify({
                "environment": current_env,
                "api_url": config.api.url,
                "presets": environment_presets,
            })

        # POST — switch environment
        data = request.json
        env = data.get("environment")
        custom_url = data.get("api_url")

        if env in environment_presets:
            new_url = environment_presets[env]
        elif env == "custom" and custom_url:
            new_url = custom_url
        else:
            return jsonify({"error": "Invalid environment or missing api_url"}), 400

        # Update config
        config.api.url = new_url
        config.api._token = None  # Clear in-memory token (keychain token may exist for new env)
        if cloud_sync:
            # The HTTP client is kept: requests carry the full URL, so it serves any host
            cloud_sync.authenticated = False
        config.save()

        # Check if we already have a token for the new environment
        has_token = bool(config.api.token)

        return jsonify({
            "success": True,
            "environment": env,
            "api_url": new_url,
            "needs_auth": not has_token,
        })

    @app.route("/api/notebooks/tree")
    def api_notebooks_tree():
        """Get folder tree structure from reMarkable metadata."""
        from app.remarkable.metadata_scanner import MetadataScanner

        config: Config = app.config["AGENT_CONFIG"]

        if not Path(config.remarkable.source_directory).exists():
            return jsonify({
                "tree": [],
                "stats": {"total_documents": 0, "total_pages": 0, "selected_pages": 0},
                "folder_missing": True,
            })

        try:
            scanner = MetadataScanner(Path(config.remarkable.source_directory))
            tree_items = scanner.scan()
            tree = scanner.to_dict(tree_items)

            # Get statistics
            total_documents = len(scanner.get_all_document_uuids())
            total_pages = scanner.count_total_pages()
            selected_pages = scanner.count_total_pages(config.sync.selected_notebooks) if not config.sync.sync_all_notebooks else total_pages

            return jsonify({
                "tree": tree,
                "stats": {
                    "total_documents": total_documents,
                    "total_pages": total_pages,
                    "selected_pages": selected_pages,
                },
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/notebooks/selection", methods=["GET", "POST"])
    def api_notebooks_selection():
        """Get or update notebook selection."""
        config: Config = app.config["AGENT_CONFIG"]

        if request.method == "GET":
            return jsonify({
                "sync_all_notebooks": config.sync.sync_all_notebooks,
                "selected_notebooks": config.sync.selected_notebooks,
            })

        # POST - Update selection
        data = request.json

        if "sync_all_notebooks" in data:
            config.sync.sync_all_notebooks = data["sync_all_notebooks"]

        if "selected_notebooks" in data:
            config.sync.selected_notebooks = data["selected_notebooks"]

        # Save configuration
        config.save()

        return jsonify({"success": True, "message": "Notebook selection updated"})

    @app.route("/api/deleted-notebooks")
    def api_deleted_notebooks():
        """Get notebooks that were deleted on the server."""
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]

        if not cloud_sync or not cloud_sync.authenticated:
            return jsonify({"deleted_notebooks": []})

        try:
            deleted = _on_loop(cloud_sync.get_deleted_notebooks(), QUICK_TIMEOUT_SECONDS)
            # Only return items that are in our excluded list (server-side tombstones)
            return jsonify({"deleted_notebooks": deleted})
        except _LOOP_ERRORS as e:
            return _loop_error(e, deleted_notebooks=[])
        except Exception as e:
            print(f"Deleted notebooks request error: {e}")
            return jsonify({"deleted_notebooks": []})

    @app.route("/api/deleted-notebooks/<uuid>/action", methods=["POST"])
    def api_deleted_notebook_action(uuid):
        """Handle re-sync or dismiss for a deleted notebook."""
        config: Config = app.config["AGENT_CONFIG"]
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]

        if not cloud_sync or not cloud_sync.authenticated:
            return jsonify({"error": "Not authenticated"}), 401

        data = request.json
        action = data.get("action", "dismiss")

        if action not in ("resync", "dismiss"):
            return jsonify({"error": "action must be 'resync' or 'dismiss'"}), 400

        try:
            # If re-syncing, remove from excluded list
            if action == "resync" and uuid in config.sync.excluded_notebooks:
                config.sync.excluded_notebooks.remove(uuid)
                config.save()

            # Acknowledge on server (removes tombstone)
            _on_loop(cloud_sync.acknowledge_deleted_notebook(uuid, action), BACKEND_TIMEOUT_SECONDS)

            return jsonify({"success": True, "action": action})
        except _LOOP_ERRORS as e:
            return _loop_error(e)
        except Exception as e:
            print(f"Deleted notebook action error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/api/quota")
    def api_quota():
        """Get quota status from backend."""
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]

        if not cloud_sync or not cloud_sync.authenticated:
            return jsonify({"error": "Not authenticated"}), 401

        try:
            quota_data = _on_loop(cloud_sync.get_quota_status(), QUICK_TIMEOUT_SECONDS)
            return jsonify(quota_data)
        except _LOOP_ERRORS as e:
            return _loop_error(e)
        except Exception as e:
            print(f"Quota status request error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/health")
    def health():
        """Health check endpoint."""
        return jsonify({"status": "healthy"})

    @app.route("/updates")
    def updates_page():
        """Updates page - check for agent updates."""
        return render_template("updates.html")

    @app.route("/api/updates/check", methods=["POST"])
    def api_check_updates():
        """Check for available agent updates."""
        from app.updater import check_for_updates

        try:
            update_info = _on_loop(check_for_updates(), QUICK_TIMEOUT_SECONDS)
        except _LOOP_ERRORS as e:
            return _loop_error(e)

        return jsonify({
            "has_update": update_info.has_update,
            "current_version": update_info.current_version,
            "latest_version": update_info.latest_version,
            "download_url": update_info.download_url,
            "release_notes": update_info.release_notes,
            "error": update_info.error,
        })
