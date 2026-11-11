"""Menu bar application using rumps."""

from pathlib import Path
from typing import Optional

import rumps

from app.browser_utils import launch_browser_app_mode
from app.config import Config
from app.tray.status import StatusRelay

# How often the main thread applies status text posted from other threads
STATUS_FLUSH_SECONDS = 0.25


class TrayApp(rumps.App):
    """rMirror Agent menu bar application."""

    def __init__(self, config: Config, agent: Optional[object] = None):
        """Initialize the menu bar app."""
        # Get the path to the icon file
        icon_path = Path(__file__).parent.parent.parent / "resources" / "menubar_icon.png"

        super().__init__(
            "rMirror",
            icon=str(icon_path) if icon_path.exists() else None,
            title=None,  # No text title when we have an icon
            quit_button=None,  # We'll add our own quit button
        )

        self.config = config
        self.agent = agent
        self.status = "Starting..."
        self.sync_count = 0

        # Create status menu item
        self.status_item = rumps.MenuItem("Status: Starting...")

        # update_status() is called from other threads; AppKit objects may only
        # be touched on the main thread, so a rumps timer (main thread) applies
        # the newest posted text.
        self._status_relay = StatusRelay(self._apply_status)
        self._status_timer = rumps.Timer(self._flush_status, STATUS_FLUSH_SECONDS)

        # Build menu
        self.menu = [
            self.status_item,
            rumps.separator,
            rumps.MenuItem("Open Web UI", callback=self.open_web_ui),
            rumps.MenuItem("Check for Updates", callback=self.check_for_updates),
            rumps.MenuItem("Settings", callback=self.open_settings),
            rumps.separator,
            rumps.MenuItem("Quit rMirror Agent", callback=self.quit_app),
        ]

    def update_status(self, status: str) -> None:
        """Update the status displayed in the menu. Safe to call from any thread."""
        self.status = status
        self._status_relay.post(status)

    def _apply_status(self, status: str) -> None:
        """Show status in the menu (main thread only)."""
        self.status_item.title = f"Status: {status}"

    def _flush_status(self, sender: object = None) -> None:
        """rumps timer callback (main thread): apply the newest posted status."""
        self._status_relay.flush()

    def run(self, **options: object) -> None:
        """Start the status timer and run the app (blocks; main thread)."""
        self._flush_status()
        self._status_timer.start()
        super().run(**options)

    def update_sync_count(self, count: int) -> None:
        """Update the sync count."""
        self.sync_count = count

    def open_web_ui(self, sender: rumps.MenuItem) -> None:
        """Open the web UI in browser."""
        url = f"http://{self.config.web.host}:{self.config.web.port}"
        launch_browser_app_mode(url, app_mode=self.config.web.app_mode)

    def open_settings(self, sender: rumps.MenuItem) -> None:
        """Open settings page in browser."""
        url = f"http://{self.config.web.host}:{self.config.web.port}"
        launch_browser_app_mode(url, app_mode=self.config.web.app_mode)

    def check_for_updates(self, sender: rumps.MenuItem) -> None:
        """Open the dashboard with updates overlay."""
        url = f"http://{self.config.web.host}:{self.config.web.port}?updates=1"
        launch_browser_app_mode(url, app_mode=self.config.web.app_mode)

    def quit_app(self, sender: rumps.MenuItem) -> None:
        """Quit the application."""
        import os

        # Stop the agent (watcher, HTTP client, event loop thread) if it exists
        if self.agent:
            self.agent.shutdown()

        # Quit the rumps application
        rumps.quit_application()

        # Force exit to ensure daemon threads (Flask, asyncio) don't keep the process alive
        os._exit(0)


def run_tray_app(config: Config, agent: Optional[object] = None) -> None:
    """Run the tray app (blocking - runs in main thread)."""
    app = TrayApp(config, agent=agent)
    app.run()
