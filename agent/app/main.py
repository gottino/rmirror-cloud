"""
rMirror Agent - Main entry point.

Monitors reMarkable Desktop app folder and syncs files to rMirror Cloud.
"""

import asyncio
import concurrent.futures
import logging
import signal
import sys
import threading
from pathlib import Path
from typing import Optional

import click

from app.agent_loop import AgentLoop, AgentLoopNotRunningError
from app.browser_utils import launch_browser_app_mode
from app.config import Config
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)


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
    ):
        """Initialize the agent."""
        self.config = config
        self.foreground = foreground
        self.running = False
        self.tray_app = tray_app
        self.loop = agent_loop if agent_loop is not None else AgentLoop()

        # Components (initialized later)
        self.file_watcher = None
        self.cloud_sync = None
        self.web_app = None
        self._web_server = None
        self.remarkable_folder_missing = False

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
        self.cloud_sync = CloudSync(self.config)

        # Start web server in background thread (before auth)
        # This ensures users can access the login page even if auth fails
        if self.config.web.enabled:
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
        try:
            await self.cloud_sync.authenticate()

            # Update tray status if authentication succeeded
            if self.tray_app:
                self.tray_app.update_status("Connected")

            # Display quota status after successful authentication
            try:
                quota_status = await self.cloud_sync.get_quota_status()
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

        # Keep running until stopped
        if self.foreground:
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

        # Keep the agent running; poll for the folder to appear if it is missing
        while self.running:
            await asyncio.sleep(5)
            if self.remarkable_folder_missing:
                if Path(self.config.remarkable.source_directory).exists():
                    self.remarkable_folder_missing = False
                    logger.info("reMarkable folder detected!")
                    print("✓ reMarkable folder detected!")
                    if self.tray_app:
                        self.tray_app.update_status("Watching" if self.cloud_sync and self.cloud_sync.authenticated else "Connected")
                    if self._can_watch():
                        self._request_watcher_start()

    def _can_watch(self) -> bool:
        return bool(
            not self.remarkable_folder_missing
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

        if not self.cloud_sync or not self.cloud_sync.authenticated:
            logger.warning("Cannot start file watcher: not authenticated")
            return False

        logger.info("Starting file watcher after authentication...")
        return self._request_watcher_start()

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

        if self._web_server:
            try:
                self._web_server.shutdown()
            except Exception as e:
                logger.warning(f"Web server shutdown failed: {e}")

        if self.loop.is_running:
            try:
                self.loop.run(self.stop(), timeout=timeout)
            except Exception as e:
                logger.warning(f"Agent did not stop cleanly: {e}")
        self.loop.stop(timeout=timeout)


def setup_signal_handlers(agent: Agent) -> None:
    """Set up signal handlers for graceful shutdown."""

    def signal_handler(sig: int, frame: object) -> None:
        print(f"\nReceived signal {sig}, initiating shutdown...")
        agent.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


@click.group(invoke_without_command=True)
@click.option("--config", "-c", type=click.Path(exists=True, path_type=Path), help="Config file path")
@click.option("--foreground", "-f", is_flag=True, help="Run in foreground (don't daemonize)")
@click.option("--debug", "-d", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx: click.Context, config: Optional[Path], foreground: bool, debug: bool) -> None:
    """rMirror Agent - Sync reMarkable tablets to the cloud."""
    # If no subcommand, run the agent
    if ctx.invoked_subcommand is None:
        run_agent(config, foreground, debug)


@cli.command()
@click.option("--config", "-c", type=click.Path(exists=True, path_type=Path), help="Config file path")
def status(config: Optional[Path]) -> None:
    """Check agent status."""
    cfg = Config.load(config)
    print("rMirror Agent Status")
    print("=" * 50)
    print(f"API URL: {cfg.api.url}")
    print(f"Email: {cfg.api.email or '(not configured)'}")
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

    # Validate configuration (only for legacy password auth)
    if not config.api.use_clerk_auth and (not config.api.email or not config.api.password):
        click.echo("Error: API credentials not configured.", err=True)
        click.echo("Run 'rmirror-agent init' to create a configuration file.", err=True)
        sys.exit(1)

    # Check if reMarkable folder exists
    remarkable_path = Path(config.remarkable.source_directory)
    remarkable_folder_missing = not remarkable_path.exists()
    if remarkable_folder_missing:
        click.echo(f"⚠️  reMarkable folder not found: {remarkable_path}", err=True)
        click.echo("The agent will start anyway. Use the web UI to configure the folder path.", err=True)

    # Create and run agent
    agent = Agent(config, foreground=foreground)
    agent.remarkable_folder_missing = remarkable_folder_missing
    setup_signal_handlers(agent)

    # Run the agent: all of its coroutines run on one long-lived loop thread
    if foreground or not config.tray.enabled:
        # Foreground mode: main thread waits for the agent
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

        agent.loop.start()
        agent_future = agent.loop.submit(agent.start())
        agent_future.add_done_callback(_log_agent_exit)

        # Run tray app in main thread (blocking)
        app.run()


def _log_agent_exit(future: "concurrent.futures.Future[None]") -> None:
    """Log an unexpected end of the agent's main coroutine (tray mode)."""
    if future.cancelled():
        return
    error = future.exception()
    if error is not None:
        logger.error(f"Agent stopped with an error: {error}", exc_info=error)


if __name__ == "__main__":
    cli()
