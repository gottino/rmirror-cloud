"""
rMirror Agent - Main entry point.

Monitors reMarkable Desktop app folder and syncs files to rMirror Cloud.
"""

import asyncio
import logging
import signal
import sys
import threading
from pathlib import Path
from typing import Optional

import click

from app.browser_utils import launch_browser_app_mode
from app.config import Config
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)


class Agent:
    """Main rMirror Agent application."""

    def __init__(self, config: Config, foreground: bool = False, tray_app: Optional[object] = None):
        """Initialize the agent."""
        self.config = config
        self.foreground = foreground
        self.running = False
        self.tray_app = tray_app

        # Components (initialized later)
        self.file_watcher = None
        self.cloud_sync = None
        self.web_app = None

    async def start(self) -> None:
        """Start the agent and all components."""
        print("Starting rMirror Agent...")
        self.running = True

        try:
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

            except Exception as e:
                # Authentication failed - log it but keep running
                print(f"\n⚠️  {e}")
                print(f"Please sign in via the web interface at http://{self.config.web.host}:{self.config.web.port}\n")

                if self.tray_app:
                    self.tray_app.update_status("Not authenticated")

            # Keep running until stopped
            if self.foreground:
                print(f"\nrMirror Agent running in foreground mode. Press Ctrl+C to stop.")
                print(f"Web UI: http://{self.config.web.host}:{self.config.web.port}")
                if self.cloud_sync and self.cloud_sync.authenticated:
                    print(f"Watching: {self.config.remarkable.source_directory}")
                print()

            # Update tray status
            if self.tray_app and self.cloud_sync and self.cloud_sync.authenticated:
                self.tray_app.update_status("Watching")

            # Start file watcher (this will block) - only if authenticated
            if self.config.remarkable.watch_enabled and self.cloud_sync and self.cloud_sync.authenticated:
                await self._run_file_watcher()
            else:
                # Keep agent running even without file watcher
                # Just wait for interrupt signal
                while self.running:
                    await asyncio.sleep(1)

        except KeyboardInterrupt:
            print("\nReceived interrupt signal, shutting down...")
        finally:
            await self.stop()

    async def _initialize_components(self) -> None:
        """Initialize all agent components."""
        # Import here to avoid circular dependencies
        from app.sync.cloud_sync import CloudSync

        # Initialize cloud sync client
        self.cloud_sync = CloudSync(self.config)
        await self.cloud_sync.authenticate()

    async def _run_file_watcher(self) -> None:
        """Run the file watcher."""
        from app.watcher.file_watcher import FileWatcher

        self.file_watcher = FileWatcher(self.config, self.cloud_sync)
        await self.file_watcher.start()

    def start_file_watcher_sync(self) -> None:
        """
        Start the file watcher after authentication (called from Flask route).
        This is called from a Flask thread, so we need to create a new task in the agent's event loop.
        """
        if self.file_watcher is not None:
            logger.info("File watcher already running")
            return

        if not self.cloud_sync or not self.cloud_sync.authenticated:
            logger.warning("Cannot start file watcher: not authenticated")
            return

        # Schedule the file watcher to start in the agent's event loop
        logger.info("Starting file watcher after authentication...")
        import threading
        watcher_thread = threading.Thread(
            target=lambda: asyncio.run(self._run_file_watcher()),
            daemon=True
        )
        watcher_thread.start()

    def _run_web_server_thread(self) -> None:
        """Run the web server in a background thread."""
        from app.web.app import create_app

        app = create_app(self.config, self.cloud_sync, agent=self)
        app.run(
            host=self.config.web.host,
            port=self.config.web.port,
            debug=False,
            use_reloader=False,
        )

    async def stop(self) -> None:
        """Stop the agent and all components."""
        print("Stopping rMirror Agent...")
        self.running = False

        if self.file_watcher:
            await self.file_watcher.stop()

        print("Agent stopped.")


def setup_signal_handlers(agent: Agent) -> None:
    """Set up signal handlers for graceful shutdown."""

    def signal_handler(sig: int, frame: object) -> None:
        print(f"\nReceived signal {sig}, initiating shutdown...")
        # Create task to stop agent
        asyncio.create_task(agent.stop())
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
    if not remarkable_path.exists():
        click.echo(f"Error: reMarkable folder not found: {remarkable_path}", err=True)
        click.echo("\nPlease ensure the reMarkable Desktop app is installed and has synced at least once.", err=True)
        sys.exit(1)

    # Create and run agent
    agent = Agent(config, foreground=foreground)
    setup_signal_handlers(agent)

    # Run the agent
    if foreground or not config.tray.enabled:
        # Foreground mode: run asyncio in main thread
        try:
            asyncio.run(agent.start())
        except KeyboardInterrupt:
            pass
    else:
        # Background mode with menu bar: run asyncio in thread, tray in main thread
        from app.tray import TrayApp

        # Create tray app
        app = TrayApp(config, agent=agent)

        # Set tray app reference in agent
        agent.tray_app = app

        # Run agent in background thread
        agent_thread = threading.Thread(
            target=lambda: asyncio.run(agent.start()),
            daemon=True,
        )
        agent_thread.start()

        # Run tray app in main thread (blocking)
        app.update_status("Idle")
        app.run()


if __name__ == "__main__":
    cli()
