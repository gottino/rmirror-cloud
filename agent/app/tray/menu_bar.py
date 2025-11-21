"""Menu bar application using rumps."""

import asyncio
import threading
import webbrowser
from typing import Optional

import rumps

from app.config import Config


class TrayApp(rumps.App):
    """rMirror Agent menu bar application."""

    def __init__(self, config: Config, agent: Optional[object] = None):
        """Initialize the menu bar app."""
        super().__init__(
            "rMirror",
            icon=None,  # Will use default icon text
            title="⚙",  # Gear icon
            quit_button=None,  # We'll add our own quit button
        )

        self.config = config
        self.agent = agent
        self.status = "Starting..."
        self.sync_count = 0

        # Create status menu item
        self.status_item = rumps.MenuItem("Status: Starting...")

        # Build menu
        self.menu = [
            self.status_item,
            rumps.separator,
            rumps.MenuItem("Open Web UI", callback=self.open_web_ui),
            rumps.MenuItem("Settings", callback=self.open_settings),
            rumps.separator,
            rumps.MenuItem("Quit rMirror Agent", callback=self.quit_app),
        ]

    def update_status(self, status: str) -> None:
        """Update the status displayed in the menu."""
        self.status = status
        self.status_item.title = f"Status: {status}"
    
    def update_sync_count(self, count: int) -> None:
        """Update the sync count."""
        self.sync_count = count
        
    def open_web_ui(self, sender: rumps.MenuItem) -> None:
        """Open the web UI in browser."""
        url = f"http://{self.config.web.host}:{self.config.web.port}"
        webbrowser.open(url)
        
    def open_settings(self, sender: rumps.MenuItem) -> None:
        """Open settings page in browser."""
        url = f"http://{self.config.web.host}:{self.config.web.port}"
        webbrowser.open(url)
        
    def quit_app(self, sender: rumps.MenuItem) -> None:
        """Quit the application."""
        # Stop the agent if it exists
        if self.agent:
            # Create a new event loop for cleanup
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.agent.stop())
            finally:
                loop.close()
        
        # Quit the rumps application
        rumps.quit_application()


def run_tray_app(config: Config, agent: Optional[object] = None) -> None:
    """Run the tray app (blocking - runs in main thread)."""
    app = TrayApp(config, agent=agent)
    app.run()
