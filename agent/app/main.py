"""
rMirror Agent - Main entry point.

Monitors reMarkable Desktop app folder and syncs files to rMirror Cloud.
"""

import asyncio
import signal
import sys
import threading
from pathlib import Path
from typing import Optional

import click

from app.config import Config


class Agent:
    """Main rMirror Agent application."""

    def __init__(self, config: Config, foreground: bool = False):
        """Initialize the agent."""
        self.config = config
        self.foreground = foreground
        self.running = False

        # Components (initialized later)
        self.file_watcher = None
        self.cloud_sync = None
        self.web_app = None
        self.tray_app = None

    async def start(self) -> None:
        """Start the agent and all components."""
        print("Starting rMirror Agent...")
        self.running = True

        try:
            # Initialize components
            await self._initialize_components()

            # Start web server in background thread
            if self.config.web.enabled:
                web_thread = threading.Thread(
                    target=self._run_web_server_thread,
                    daemon=True,
                )
                web_thread.start()

            # Keep running until stopped
            if self.foreground:
                print("\nrMirror Agent running in foreground mode. Press Ctrl+C to stop.")
                print(f"Web UI: http://{self.config.web.host}:{self.config.web.port}")
                print(f"Watching: {self.config.remarkable.source_directory}\n")

            # Start file watcher (this will block)
            if self.config.remarkable.watch_enabled:
                await self._run_file_watcher()

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

    def _run_web_server_thread(self) -> None:
        """Run the web server in a background thread."""
        from app.web.app import create_app

        app = create_app(self.config, self.cloud_sync)
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
    # Load configuration
    config = Config.load(config_path)

    # Validate configuration
    if not config.api.email or not config.api.password:
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
    try:
        asyncio.run(agent.start())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli()
