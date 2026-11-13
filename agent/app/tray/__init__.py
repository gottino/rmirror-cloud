"""System tray integration for rMirror Agent."""

__all__ = ["TrayApp"]


def __getattr__(name: str) -> object:
    # Import rumps (via menu_bar) only when the tray app is actually used, so
    # app.tray.status stays importable where rumps is not installed.
    if name == "TrayApp":
        from app.tray.menu_bar import TrayApp

        return TrayApp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
