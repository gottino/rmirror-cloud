"""
Thread-safe hand-off of status text to the menu bar.

rumps/AppKit objects may only be touched on the main thread, but status
updates come from the agent loop thread, Flask threads and the watchdog
thread. ``post()`` only stores the latest text; ``flush()`` runs on the main
thread (from a rumps timer) and applies it. No rumps import here, so this is
testable on any platform.
"""

import threading
from collections.abc import Callable


class StatusRelay:
    """Latest-value mailbox between any thread and the main thread."""

    def __init__(self, apply: Callable[[str], None]):
        """
        Args:
            apply: Called with the newest status text; only ever from flush()
        """
        self._apply = apply
        self._lock = threading.Lock()
        self._pending: str | None = None

    def post(self, status: str) -> None:
        """Remember status as the text to show next. Safe from any thread."""
        with self._lock:
            self._pending = status

    def flush(self) -> bool:
        """Apply the newest posted status, if any. Call on the main thread.

        Returns True if a status was applied.
        """
        with self._lock:
            status, self._pending = self._pending, None
        if status is None:
            return False
        self._apply(status)
        return True
