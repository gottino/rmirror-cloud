"""
rMirror Agent - Main entry point.

Monitors reMarkable Desktop app folder and syncs files to rMirror Cloud.
"""

import asyncio
import concurrent.futures
import errno
import logging
import os
import select
import signal
import socket
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Optional

import click

from app.agent_loop import AgentLoop, AgentLoopNotRunningError
from app.browser_utils import launch_browser_app_mode
from app.config import Config
from app.logging_config import setup_logging
from app.remarkable.library import FOLDER_MISSING, FOLDER_OK, FOLDER_UNREADABLE, folder_state
from app.sync.quota_cache import QuotaCache

logger = logging.getLogger(__name__)

# Headless mode (rMirror for Mac 2.0, see docs/local-api.md)
APP_TOKEN_ENV = "RMIRROR_APP_TOKEN"
MIN_APP_TOKEN_LENGTH = 32
READY_LINE = "RMIRROR_CORE_READY port={port} api=2"
HEADLESS_HOST = "127.0.0.1"
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_PORT_IN_USE = 3
EXIT_BAD_APP_TOKEN = 4
# How long each shutdown step may take in headless mode (the app waits 8 s after SIGTERM)
HEADLESS_SHUTDOWN_STEP_SECONDS = 1.5
HEADLESS_HOST_V6 = "::1"

# Sign-in state reported as auth.state by GET /api/v2/state (headless mode)
AUTH_CHECKING = "checking"
AUTH_SIGNED_IN = "signed_in"
AUTH_SIGNED_OUT = "signed_out"
AUTH_OFFLINE = "offline"
# Retry of the stored sign-in check while the cloud cannot be reached
AUTH_RETRY_FIRST_SECONDS = 5.0
AUTH_RETRY_MAX_SECONDS = 60.0


class Agent:
    """Main rMirror Agent application.

    Threads: the agent's coroutines (start, the file watcher and its sync queue
    worker, CloudSync and its HTTP client) all run on one AgentLoop thread. The
    web server runs in its own thread and hands coroutines to that loop. In tray
    mode rumps owns the main thread.
    """

    # File watcher states (guarded by _watcher_lock)
    WATCHER_IDLE = "idle"
    WATCHER_STARTING = "starting"
    WATCHER_RUNNING = "running"

    def __init__(
        self,
        config: Config,
        foreground: bool = False,
        tray_app: Optional[object] = None,
        agent_loop: AgentLoop | None = None,
        headless: bool = False,
        app_token: str | None = None,
    ):
        """Initialize the agent.

        ``headless``: run for the native app (no tray, no browser); the web server is
        bound by ``bind_web_server()`` before start() and the local API v2 requires
        ``app_token``.
        """
        self.config = config
        self.foreground = foreground
        self.headless = headless
        self.app_token = app_token
        self.running = False
        self.tray_app = tray_app
        self.loop = agent_loop if agent_loop is not None else AgentLoop()

        # Components (initialized later)
        self.file_watcher = None
        self.cloud_sync = None
        self.web_app = None
        self._web_server = None
        self.remarkable_folder_missing = False
        # The folder exists but cannot be listed (macOS privacy protection): no
        # watcher until it becomes readable (a scan would see an empty folder)
        self.remarkable_folder_unreadable = False
        self.quota_cache = QuotaCache()
        self._account_refresh_task: asyncio.Task | None = None
        # Headless: state of the stored sign-in (see AUTH_*), and its retry task
        self.auth_state = AUTH_SIGNED_OUT
        self._auth_retry_task: asyncio.Task | None = None
        self._auth_retry_sleep = asyncio.sleep  # injectable for tests
        # Folder whose existing files must be baselined before the next watcher
        # starts on it (set when the user switches folders through the local API)
        self._baseline_pending: str | None = None
        # Headless: the [::1] server next to the 127.0.0.1 one
        self._extra_web_servers: list = []

        self._watcher_lock = threading.Lock()
        self._watcher_state = self.WATCHER_IDLE
        self._watcher_task: asyncio.Task | None = None
        self._shutdown_lock = threading.Lock()
        self._shut_down = False

    async def start(self) -> None:
        """Start the agent and all components. Runs on the agent loop until shutdown()."""
        print("Starting rMirror Agent...")
        self.running = True

        # Update tray status
        if self.tray_app:
            self.tray_app.update_status("Starting...")

        # Initialize CloudSync object BEFORE starting web server
        # This way the web server has a reference to the actual object
        from app.sync.cloud_sync import CloudSync
        if self.cloud_sync is None:
            self.cloud_sync = CloudSync(self.config)

        # Start web server in background thread (before auth)
        # This ensures users can access the login page even if auth fails.
        # (Headless mode has bound and started its server before start().)
        if self.config.web.enabled and self._web_server is None:
            web_thread = threading.Thread(
                target=self._run_web_server_thread,
                daemon=True,
            )
            web_thread.start()
            # Give the web server a moment to start
            await asyncio.sleep(0.5)

            # Auto-launch browser if configured
            if self.config.web.auto_launch_browser:
                url = f"http://{self.config.web.host}:{self.config.web.port}"
                launch_browser_app_mode(url, app_mode=self.config.web.app_mode)
                print(f"Opened web UI in browser: {url}")

        # Try to authenticate
        if self.headless:
            # Never blocks start-up: offline -> retried in the background
            await self._initial_sign_in_check()
        else:
            await self._legacy_sign_in_check()

        # Keep running until stopped
        await self._run_until_stopped()

    async def _legacy_sign_in_check(self) -> None:
        """Tray / foreground mode: check the stored sign-in once at start-up (unchanged)."""
        try:
            await self.cloud_sync.authenticate()

            # Update tray status if authentication succeeded
            if self.tray_app:
                self.tray_app.update_status("Connected")

            # Display quota status after successful authentication
            try:
                quota_status = await self.cloud_sync.get_quota_status()
                self.quota_cache.store(quota_status, host=self.config.api._keychain_user_id)
                self.quota_cache.note_attempt()
                quota_display = self.cloud_sync.format_quota_display(quota_status)
                print(f"\n{quota_display}\n")
                logger.info(f"Quota: {quota_status['used']}/{quota_status['limit']} pages used")
            except Exception as quota_error:
                logger.warning(f"Could not fetch quota status: {quota_error}")
                # Don't block startup if quota fetch fails

        except Exception as e:
            # Authentication failed - log it but keep running
            print(f"\n⚠️  {e}")
            print(f"Please sign in via the web interface at http://{self.config.web.host}:{self.config.web.port}\n")

            if self.tray_app:
                self.tray_app.update_status("Not authenticated")

    async def _initial_sign_in_check(self) -> None:
        """Headless: checking -> signed_in / signed_out / offline (then retried)."""
        has_token = await asyncio.to_thread(lambda: bool(self.config.api.token))
        if not has_token:
            self.auth_state = AUTH_SIGNED_OUT
            return
        self.auth_state = AUTH_CHECKING
        await self._check_sign_in()

    async def _check_sign_in(self) -> bool:
        """Verify the stored sign-in with the cloud and update auth_state. Never raises."""
        from app.sync.cloud_sync import AuthenticationRequiredError

        try:
            await self.cloud_sync.authenticate()
        except AuthenticationRequiredError:
            self.auth_state = AUTH_SIGNED_OUT
            return False
        except Exception as e:
            if self.auth_state != AUTH_OFFLINE:
                logger.warning(
                    f"Could not reach rMirror Cloud to check the sign-in ({type(e).__name__}); "
                    "retrying in the background"
                )
            self.auth_state = AUTH_OFFLINE
            self._schedule_auth_retry()
            return False
        if self.auth_state == AUTH_OFFLINE:
            logger.info("rMirror Cloud reachable again; sign-in confirmed")
        self.auth_state = AUTH_SIGNED_IN
        self.quota_cache.mark_stale()  # quota and account email on the next tick
        self._maybe_refresh_account()
        if self._can_watch():
            self._request_watcher_start()
        return True

    def _schedule_auth_retry(self) -> None:
        if self._auth_retry_task is not None and not self._auth_retry_task.done():
            return
        self._auth_retry_task = asyncio.get_running_loop().create_task(self._auth_retry_loop())

    async def _auth_retry_loop(self) -> None:
        """Retry the sign-in check with backoff (5 s doubling up to 60 s) while offline."""
        delay = AUTH_RETRY_FIRST_SECONDS
        while self.running and self.auth_state == AUTH_OFFLINE:
            await self._auth_retry_sleep(delay)
            if not self.running or self.auth_state != AUTH_OFFLINE:
                return
            if self.cloud_sync and self.cloud_sync.authenticated:
                self.auth_state = AUTH_SIGNED_IN  # signed in through the browser meanwhile
                return
            if await self._check_sign_in():
                return
            delay = min(delay * 2, AUTH_RETRY_MAX_SECONDS)

    async def _run_until_stopped(self) -> None:
        """After the sign-in check: start watching and poll until shutdown."""
        if self.foreground and not self.headless:
            print("\nrMirror Agent running in foreground mode. Press Ctrl+C to stop.")
            print(f"Web UI: http://{self.config.web.host}:{self.config.web.port}")
            if self.cloud_sync and self.cloud_sync.authenticated:
                print(f"Watching: {self.config.remarkable.source_directory}")
            print()

        # Update tray status
        if self.remarkable_folder_missing:
            if self.tray_app:
                self.tray_app.update_status("Folder not found")
            print("⚠️  reMarkable folder not found. Waiting for folder or custom path...")
        elif self.tray_app and self.cloud_sync and self.cloud_sync.authenticated:
            self.tray_app.update_status("Watching")

        # Start file watcher - only if authenticated and folder exists
        if self._can_watch():
            self._request_watcher_start()

        if self.remarkable_folder_unreadable:
            print("⚠️  reMarkable folder cannot be read (Full Disk Access?). Waiting for access...")

        # Keep the agent running; poll for the folder to appear if it is missing
        # (or to become readable if access to it is blocked)
        while self.running:
            await asyncio.sleep(5)
            if self.remarkable_folder_missing:
                if Path(self.config.remarkable.source_directory).exists():
                    self.remarkable_folder_missing = False
                    if folder_state(self.config.remarkable.source_directory) == FOLDER_UNREADABLE:
                        self.remarkable_folder_unreadable = True
                        logger.warning("reMarkable folder detected but cannot be read")
                        continue
                    logger.info("reMarkable folder detected!")
                    print("✓ reMarkable folder detected!")
                    if self.tray_app:
                        self.tray_app.update_status("Watching" if self.cloud_sync and self.cloud_sync.authenticated else "Connected")
                    if self._can_watch():
                        self._request_watcher_start()
            elif self.remarkable_folder_unreadable:
                state = folder_state(self.config.remarkable.source_directory)
                if state != FOLDER_UNREADABLE:
                    self.remarkable_folder_unreadable = False
                    self.remarkable_folder_missing = state == FOLDER_MISSING
                    if state == FOLDER_OK:
                        logger.info("reMarkable folder is readable now")
                        print("✓ reMarkable folder is readable now")
                        if self._can_watch():
                            self._request_watcher_start()
            if self.headless:
                self._maybe_refresh_account()

    def _can_watch(self) -> bool:
        return bool(
            not self.remarkable_folder_missing
            and not self.remarkable_folder_unreadable
            and self.config.remarkable.watch_enabled
            and self.cloud_sync
            and self.cloud_sync.authenticated
        )

    async def _initialize_components(self) -> None:
        """Initialize all agent components."""
        # Import here to avoid circular dependencies
        from app.sync.cloud_sync import CloudSync

        # Initialize cloud sync client
        self.cloud_sync = CloudSync(self.config)
        await self.cloud_sync.authenticate()

    async def _run_file_watcher(self) -> None:
        """Run the file watcher (on the agent loop; returns when the watcher stops)."""
        from app.watcher.file_watcher import FileWatcher

        with self._watcher_lock:
            self._watcher_state = self.WATCHER_RUNNING
        self.file_watcher = FileWatcher(self.config, self.cloud_sync, on_status=self._set_tray_status)
        pending = self._baseline_pending
        if pending is not None and pending == self.config.remarkable.source_directory:
            # A folder chosen through the local API: its existing files are a
            # baseline, not changes to upload (first-sync rule)
            await self._baseline_current_folder(self.file_watcher)
            self._baseline_pending = None
        if self.headless:
            self.file_watcher.sync_queue.on_batch_complete = self._on_upload_batch
        await self.file_watcher.start()

    def _request_watcher_start(self) -> bool:
        """Schedule the file watcher on the agent loop, unless one is starting or running.

        Safe to call from any thread. Returns True if a watcher was scheduled.
        """
        with self._watcher_lock:
            if self._watcher_state != self.WATCHER_IDLE:
                logger.info(f"File watcher already {self._watcher_state}")
                return False
            self._watcher_state = self.WATCHER_STARTING
        try:
            self.loop.call_soon(self._spawn_watcher_task)
        except AgentLoopNotRunningError:
            with self._watcher_lock:
                self._watcher_state = self.WATCHER_IDLE
            logger.warning("Cannot start file watcher: agent loop is not running")
            return False
        return True

    def _spawn_watcher_task(self) -> None:
        """Create the watcher task (runs on the agent loop thread)."""
        if self._shut_down:
            with self._watcher_lock:
                self._watcher_state = self.WATCHER_IDLE
            return
        task = asyncio.get_running_loop().create_task(self._run_file_watcher())
        self._watcher_task = task
        task.add_done_callback(self._on_watcher_done)

    def _on_watcher_done(self, task: "asyncio.Task[None]") -> None:
        with self._watcher_lock:
            self._watcher_state = self.WATCHER_IDLE
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.error(f"File watcher stopped with an error: {error}", exc_info=error)
            print(f"⚠️  File watcher stopped: {error}")

    def _set_tray_status(self, status: str) -> None:
        """Show a status in the menu bar, if there is one."""
        if self.tray_app:
            self.tray_app.update_status(status)

    def start_file_watcher_sync(self) -> bool:
        """
        Start the file watcher after authentication (called from a Flask thread).

        Schedules the watcher on the agent loop and returns immediately. Idempotent:
        does nothing while a watcher is starting or running. Returns True if a
        watcher was scheduled.
        """
        if not Path(self.config.remarkable.source_directory).exists():
            logger.warning("Cannot start file watcher: reMarkable folder not found")
            return False

        self.remarkable_folder_missing = False

        if folder_state(self.config.remarkable.source_directory) == FOLDER_UNREADABLE:
            # The agent loop starts the watcher once the folder becomes readable
            self.remarkable_folder_unreadable = True
            logger.warning("Cannot start file watcher yet: reMarkable folder cannot be read")
            return False
        self.remarkable_folder_unreadable = False

        if not self.cloud_sync or not self.cloud_sync.authenticated:
            logger.warning("Cannot start file watcher: not authenticated")
            return False

        logger.info("Starting file watcher after authentication...")
        return self._request_watcher_start()

    @property
    def watcher_state(self) -> str:
        """idle, starting or running."""
        with self._watcher_lock:
            return self._watcher_state

    def update_folder_flags(self) -> str:
        """Re-check the reMarkable folder and update the missing/unreadable flags."""
        state = folder_state(self.config.remarkable.source_directory)
        self.remarkable_folder_missing = state == FOLDER_MISSING
        self.remarkable_folder_unreadable = state == FOLDER_UNREADABLE
        return state

    async def _baseline_current_folder(self, file_watcher) -> None:
        from app.watcher.file_watcher import ReMarkableEventHandler, baseline_folder

        handler = ReMarkableEventHandler(file_watcher.sync_queue, self.config)
        await asyncio.to_thread(
            baseline_folder,
            Path(self.config.remarkable.source_directory),
            handler,
            file_watcher.sync_queue.manifest,
        )

    async def change_source_directory(self, new_directory: str) -> str:
        """Switch to another reMarkable folder (agent loop). Returns the new folder state.

        Stops the watcher, saves the folder, and makes sure the files already in the
        new folder are recorded as baseline (not uploaded) before a watcher runs on
        it: the next watcher start does that first. Starts the watcher again if it can.
        """
        await self.stop_file_watcher()
        self.config.remarkable.source_directory = new_directory
        await asyncio.to_thread(self.config.save)
        self._baseline_pending = new_directory
        state = self.update_folder_flags()
        if self._can_watch():
            self._request_watcher_start()
        return state

    async def stop_file_watcher(self) -> None:
        """Stop the running file watcher, if any (runs on the agent loop)."""
        file_watcher = self.file_watcher
        if file_watcher is not None:
            await file_watcher.stop()
        task = self._watcher_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except BaseException:  # Cancelled, or the error already logged by _on_watcher_done
                pass
        self.file_watcher = None

    # ------------------------------------------------------------------
    # Account cache (quota, email) for the local API v2 (headless mode)
    # ------------------------------------------------------------------

    def _on_upload_batch(self, stats: dict) -> None:
        """Sync queue callback (agent loop): quota changes after uploads."""
        if stats.get("uploaded"):
            self.quota_cache.mark_stale()

    def request_account_refresh(self) -> None:
        """Refresh quota (and the account email) soon on the agent loop. Safe from any thread."""
        self.quota_cache.mark_stale()
        try:
            self.loop.call_soon(self._maybe_refresh_account)
        except AgentLoopNotRunningError:
            pass

    def _maybe_refresh_account(self) -> None:
        """Start a refresh task if one is due (agent loop thread)."""
        if not (self.cloud_sync and self.cloud_sync.authenticated):
            return
        if self._account_refresh_task is not None and not self._account_refresh_task.done():
            return
        if not self.quota_cache.refresh_due():
            return
        self.quota_cache.note_attempt()
        self._account_refresh_task = asyncio.get_running_loop().create_task(self.refresh_account())

    async def refresh_account(self) -> None:
        """Fetch quota (and the email if unknown) into the cache. Never raises."""
        cloud_sync = self.cloud_sync
        if not (cloud_sync and cloud_sync.authenticated):
            return
        host = self.config.api._keychain_user_id
        try:
            self.quota_cache.store(await cloud_sync.get_quota_status(), host=host)
        except Exception as e:
            logger.warning(f"Could not refresh quota: {type(e).__name__}")
        if cloud_sync.authenticated and not cloud_sync.user_email:
            try:
                await cloud_sync.get_user_info()
            except Exception as e:
                logger.warning(f"Could not fetch account info: {type(e).__name__}")

    async def reauthenticate(self) -> bool:
        """Check the stored sign-in again (e.g. after switching environment). Never raises."""
        if not self.cloud_sync:
            return False
        self.auth_state = AUTH_CHECKING
        return await self._check_sign_in()

    # ------------------------------------------------------------------
    # Web server
    # ------------------------------------------------------------------

    def bind_web_server(self) -> int:
        """Headless mode: bind 127.0.0.1:<web.port> and build the server (not serving yet).

        Raises OSError (errno EADDRINUSE if another process has the port). Returns the port.
        """
        from werkzeug.serving import make_server

        from app.sync.cloud_sync import CloudSync
        from app.web.app import create_app

        if self.cloud_sync is None:
            self.cloud_sync = CloudSync(self.config)

        port = self.config.web.port
        # 127.0.0.1 and [::1]: the dashboard returns the sign-in to "localhost",
        # which a browser may resolve to either, so nothing else may hold the other
        listener = bind_listen_socket(HEADLESS_HOST, port)
        try:
            listener_v6 = bind_listen_socket(HEADLESS_HOST_V6, port, socket.AF_INET6)
        except OSError as e:
            if e.errno == errno.EADDRINUSE:
                listener.close()
                raise
            # No IPv6 loopback on this Mac: nobody else can listen there either
            logger.warning(f"Not listening on [::1] ({e.strerror})")
            listener_v6 = None
        try:
            app = create_app(
                self.config,
                self.cloud_sync,
                agent=self,
                agent_loop=self.loop,
                app_token=self.app_token,
                headless=True,
            )
            # werkzeug takes over duplicates of the bound, listening sockets
            self._web_server = make_server(
                HEADLESS_HOST, port, app, threaded=True, fd=listener.fileno()
            )
            if listener_v6 is not None:
                self._extra_web_servers.append(
                    make_server(HEADLESS_HOST_V6, port, app, threaded=True, fd=listener_v6.fileno())
                )
        finally:
            listener.close()
            if listener_v6 is not None:
                listener_v6.close()
        return port

    def serve_web_server_in_background(self) -> None:
        """Serve the server built by bind_web_server() on a daemon thread."""
        server = self._web_server
        if server is None:
            raise RuntimeError("bind_web_server() first")
        for index, srv in enumerate([server, *self._extra_web_servers]):
            threading.Thread(target=srv.serve_forever, name=f"rmirror-web-{index}", daemon=True).start()

    def _run_web_server_thread(self) -> None:
        """Run the web server in a background thread."""
        from app.web.app import create_app

        app = create_app(self.config, self.cloud_sync, agent=self, agent_loop=self.loop)

        # Use SO_REUSEADDR to avoid "Address already in use" on restart
        from werkzeug.serving import make_server
        server = make_server(
            self.config.web.host,
            self.config.web.port,
            app,
        )
        server.socket.setsockopt(
            __import__('socket').SOL_SOCKET,
            __import__('socket').SO_REUSEADDR,
            1,
        )
        self._web_server = server
        server.serve_forever()

    async def stop(self) -> None:
        """Stop the agent's loop-side components (runs on the agent loop)."""
        print("Stopping rMirror Agent...")
        self.running = False

        if self.file_watcher:
            await self.file_watcher.stop()

        task = self._watcher_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except BaseException:  # Cancelled, or the error already logged by _on_watcher_done
                pass

        # Close the long-lived HTTP client on the loop it belongs to
        if self.cloud_sync:
            await self.cloud_sync.close()

        print("Agent stopped.")

    def shutdown(self, timeout: float = 15.0) -> None:
        """Stop everything and join the loop thread. Safe from any thread but the loop's.

        Order: web server first (no new work arrives), then the watcher, queue worker
        and HTTP client on the loop, then the loop itself. Idempotent.
        """
        with self._shutdown_lock:
            if self._shut_down:
                return
            self._shut_down = True

        self.running = False

        for server in [self._web_server, *self._extra_web_servers]:
            if not server:
                continue
            try:
                server.shutdown()
            except Exception as e:
                logger.warning(f"Web server shutdown failed: {e}")

        if self.loop.is_running:
            try:
                self.loop.run(self.stop(), timeout=timeout)
            except Exception as e:
                logger.warning(f"Agent did not stop cleanly: {e}")
        self.loop.stop(timeout=timeout)
        logger.info("rMirror Agent stopped")


def setup_signal_handlers(agent: Agent, quit_app: Callable[[], None] | None = None) -> None:
    """Set up SIGINT/SIGTERM handlers for graceful shutdown.

    Args:
        agent: The agent to shut down
        quit_app: Tray mode: quits the menu-bar app (the same path as its Quit item).
            Python runs signal handlers on the main thread, which in tray mode is
            inside the AppKit run loop; sys.exit() there is swallowed and the process
            stays alive with a menu-bar icon, so the app has to be quit instead.
    """

    def signal_handler(sig: int, frame: object) -> None:
        name = signal.Signals(sig).name
        logger.info(f"Received {name}, shutting down")
        print(f"\nReceived {name}, initiating shutdown...")
        agent.shutdown()
        if quit_app is not None:
            quit_app()
        else:
            sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def bind_listen_socket(host: str, port: int, family: int = socket.AF_INET) -> socket.socket:
    """A TCP socket bound to host:port and listening. Raises OSError (EADDRINUSE if taken)."""
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        # Same as werkzeug/http.server: allows a restart while old connections linger
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if family == socket.AF_INET6:
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        sock.bind((host, port))
        sock.listen(128)
    except BaseException:
        sock.close()
        raise
    return sock


def read_app_token(environ: "os._Environ[str] | dict[str, str]") -> str | None:
    """The app token from the environment, or None if missing or too short."""
    token = (environ.get(APP_TOKEN_ENV) or "").strip()
    if len(token) < MIN_APP_TOKEN_LENGTH:
        return None
    return token


def parent_already_gone(stream) -> bool:
    """True if stdin is missing, closed, or already at end of file (the app is gone)."""
    if stream is None or getattr(stream, "closed", False):
        return True
    try:
        fd = stream.fileno()
        os.fstat(fd)
        readable, _, _ = select.select([fd], [], [], 0)
        # The app never writes to the pipe: readable means end of file
        return bool(readable) and os.read(fd, 1) == b""
    except (OSError, ValueError):
        return True


def quiet_stdout_after_ready() -> None:
    """Headless: after the ready line, stdout stays quiet (logs still go to agent.log).

    The app must keep draining stdout anyway (docs/local-api.md).
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        if isinstance(handler, logging.StreamHandler) and getattr(handler, "stream", None) in (
            sys.stdout,
            sys.__stdout__,
        ):
            root.removeHandler(handler)
    sys.stdout.flush()
    sys.stdout = open(os.devnull, "w")  # noqa: SIM115 (lives as long as the process)


def watch_parent_stdin(on_eof: Callable[[], None], stream=None) -> threading.Thread:
    """Call on_eof when stdin reaches end of file (the parent app is gone).

    Runs on a daemon thread. The app keeps the write end of the pipe open for its
    whole life and never writes, so EOF means it exited or crashed.
    """
    fd = (stream if stream is not None else sys.stdin).fileno()

    def watch() -> None:
        try:
            while os.read(fd, 4096):
                pass
        except OSError as e:
            logger.warning(f"Reading stdin failed ({e}); treating it as closed")
        logger.info("stdin closed: the app is gone, shutting down")
        on_eof()

    thread = threading.Thread(target=watch, name="rmirror-parent-watch", daemon=True)
    thread.start()
    return thread


@click.group(invoke_without_command=True)
@click.option("--config", "-c", type=click.Path(exists=True, path_type=Path), help="Config file path")
@click.option("--foreground", "-f", is_flag=True, help="Run in foreground (don't daemonize)")
@click.option("--debug", "-d", is_flag=True, help="Enable debug logging")
@click.option(
    "--headless",
    is_flag=True,
    help="Run as the core of the native app: no menu bar, no browser (needs RMIRROR_APP_TOKEN)",
)
@click.pass_context
def cli(ctx: click.Context, config: Optional[Path], foreground: bool, debug: bool, headless: bool) -> None:
    """rMirror Agent - Sync reMarkable tablets to the cloud."""
    # If no subcommand, run the agent
    if ctx.invoked_subcommand is None:
        if headless:
            sys.exit(run_headless(config, debug))
        run_agent(config, foreground, debug)


@cli.command()
@click.option("--config", "-c", type=click.Path(exists=True, path_type=Path), help="Config file path")
def status(config: Optional[Path]) -> None:
    """Check agent status."""
    cfg = Config.load(config)
    print("rMirror Agent Status")
    print("=" * 50)
    print(f"API URL: {cfg.api.url}")
    print(f"reMarkable folder: {cfg.remarkable.source_directory}")
    print(f"Watch enabled: {cfg.remarkable.watch_enabled}")
    print(f"Web UI: {'Enabled' if cfg.web.enabled else 'Disabled'}")
    if cfg.web.enabled:
        print(f"Web UI URL: http://{cfg.web.host}:{cfg.web.port}")
    print(f"Auto-sync: {'Enabled' if cfg.sync.auto_sync else 'Disabled'}")


@cli.command()
def init() -> None:
    """Initialize configuration file."""
    config_path = Config.get_default_config_path()

    if config_path.exists():
        click.confirm(
            f"Config file already exists at {config_path}. Overwrite?", abort=True
        )

    # Create default config
    config = Config()
    config.save(config_path)

    click.echo(f"\nConfiguration file created at: {config_path}")
    click.echo("\nPlease edit the file to add your rMirror Cloud credentials:")
    click.echo(f"  {config_path}")
    click.echo("\nThen run: rmirror-agent")


def run_agent(config_path: Optional[Path], foreground: bool, debug: bool) -> None:
    """Run the agent."""
    # Set up logging first
    log_level = "DEBUG" if debug else "INFO"
    setup_logging(log_level)
    logger.info("=" * 60)
    logger.info("rMirror Agent starting up")
    logger.info(f"Log level: {log_level}")
    logger.info("=" * 60)

    # Load configuration
    config = Config.load(config_path)

    # Check if reMarkable folder exists
    remarkable_path = Path(config.remarkable.source_directory)
    remarkable_folder_missing = not remarkable_path.exists()
    if remarkable_folder_missing:
        click.echo(f"⚠️  reMarkable folder not found: {remarkable_path}", err=True)
        click.echo("The agent will start anyway. Use the web UI to configure the folder path.", err=True)

    # Create and run agent
    agent = Agent(config, foreground=foreground)
    agent.remarkable_folder_missing = remarkable_folder_missing
    agent.remarkable_folder_unreadable = (
        not remarkable_folder_missing and folder_state(remarkable_path) == FOLDER_UNREADABLE
    )

    # Run the agent: all of its coroutines run on one long-lived loop thread
    if foreground or not config.tray.enabled:
        # Foreground mode: main thread waits for the agent
        setup_signal_handlers(agent)
        agent.loop.start()
        try:
            agent.loop.submit(agent.start()).result()
        except (KeyboardInterrupt, concurrent.futures.CancelledError):
            pass
        finally:
            agent.shutdown()
    else:
        # Background mode with menu bar: agent on the loop thread, tray in main thread
        from app.tray import TrayApp

        # Create tray app
        app = TrayApp(config, agent=agent)

        # Set tray app reference in agent
        agent.tray_app = app
        app.update_status("Idle")
        setup_signal_handlers(agent, quit_app=app.shutdown_and_quit)

        agent.loop.start()
        agent_future = agent.loop.submit(agent.start())
        agent_future.add_done_callback(_log_agent_exit)

        # Run tray app in main thread (blocking)
        app.run()


def run_headless(config_path: Optional[Path], debug: bool, stdin=None) -> int:
    """Run as the native app's core process; returns the exit code (see docs/local-api.md).

    Never imports rumps and never opens a browser. Binds 127.0.0.1:<web.port>,
    prints the ready line once the server is listening, stops cleanly on SIGTERM,
    SIGINT or when stdin closes.
    """
    app_token = read_app_token(os.environ)
    # Keep the token out of anything this process starts later
    os.environ.pop(APP_TOKEN_ENV, None)
    if app_token is None:
        print(f"{APP_TOKEN_ENV} is missing or shorter than {MIN_APP_TOKEN_LENGTH} characters", file=sys.stderr)
        return EXIT_BAD_APP_TOKEN

    stdin = sys.stdin if stdin is None else stdin
    if parent_already_gone(stdin):
        # Started without a parent holding stdin open: nothing to serve
        return EXIT_OK

    try:
        setup_logging("DEBUG" if debug else "INFO")
        logger.info("rMirror core starting up (headless)")
        config = Config.load(config_path)
        agent = Agent(config, foreground=True, headless=True, app_token=app_token)
        agent.update_folder_flags()
        try:
            port = agent.bind_web_server()
        except OSError as e:
            if e.errno == errno.EADDRINUSE:
                logger.error(f"Port {config.web.port} is already in use")
                print(f"Port {config.web.port} is already in use", file=sys.stderr)
                return EXIT_PORT_IN_USE
            raise
    except Exception as e:
        logger.error(f"rMirror core failed to start: {e}", exc_info=True)
        return EXIT_ERROR

    return _serve_headless(agent, port, stdin)


def _serve_headless(agent: Agent, port: int, stdin=None) -> int:
    """Run a bound headless agent until it is asked to stop; returns the exit code."""
    stop_requested = threading.Event()
    finished = threading.Event()

    def request_stop() -> None:
        stop_requested.set()
        finished.set()

    def on_signal(sig: int, frame: object) -> None:
        logger.info(f"Received {signal.Signals(sig).name}, shutting down")
        request_stop()

    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)

    exit_code = EXIT_OK
    try:
        agent.loop.start()
        agent.serve_web_server_in_background()
        print(READY_LINE.format(port=port), flush=True)
        quiet_stdout_after_ready()
        watch_parent_stdin(request_stop, stream=stdin)

        future = agent.loop.submit(agent.start())
        future.add_done_callback(lambda _f: finished.set())
        # Wake up regularly so signal handlers run promptly on the main thread
        while not finished.wait(0.5):
            pass
        if not stop_requested.is_set():
            error = None if future.cancelled() else future.exception()
            if error is not None:
                logger.error(f"Agent stopped with an error: {error}", exc_info=error)
                exit_code = EXIT_ERROR
    except Exception as e:
        logger.error(f"rMirror core failed: {e}", exc_info=True)
        exit_code = EXIT_ERROR
    finally:
        agent.shutdown(timeout=HEADLESS_SHUTDOWN_STEP_SECONDS)
    return exit_code


def _log_agent_exit(future: "concurrent.futures.Future[None]") -> None:
    """Log an unexpected end of the agent's main coroutine (tray mode)."""
    if future.cancelled():
        return
    error = future.exception()
    if error is not None:
        logger.error(f"Agent stopped with an error: {error}", exc_info=error)


if __name__ == "__main__":
    cli()
