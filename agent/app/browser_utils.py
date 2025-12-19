"""Browser utilities for launching web UI."""

import logging
import platform
import subprocess
import webbrowser
from pathlib import Path

logger = logging.getLogger(__name__)


def launch_browser_app_mode(url: str, app_mode: bool = True) -> None:
    """
    Launch browser in app mode (without browser chrome).

    Args:
        url: URL to open
        app_mode: If True, launch in app mode. If False, use standard browser.
    """
    system = platform.system()

    if not app_mode:
        # Just use default browser
        webbrowser.open(url)
        return

    try:
        if system == "Darwin":  # macOS
            if app_mode:
                # Try to detect if default browser is Chrome and use app mode
                chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
                if Path(chrome_path).exists():
                    # Check if Chrome is default browser (best effort)
                    try:
                        result = subprocess.run(
                            ["defaults", "read", "com.apple.LaunchServices/com.apple.launchservices.secure", "LSHandlers"],
                            capture_output=True,
                            text=True,
                            timeout=1
                        )
                        # If Chrome is mentioned as handler for http, use app mode
                        if "chrome" in result.stdout.lower():
                            subprocess.Popen([chrome_path, f"--app={url}"],
                                           stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL)
                            logger.info(f"Launched Chrome (default) in app mode: {url}")
                            return
                    except Exception:
                        pass  # Fall through to default browser

            # Use default browser (Safari, Chrome, Firefox, etc.)
            webbrowser.open(url)
            logger.info(f"Launched default browser: {url}")

        elif system == "Windows":
            # Try Chrome
            import winreg
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe")
                chrome_path, _ = winreg.QueryValueEx(key, "")
                subprocess.Popen([chrome_path, f"--app={url}"],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
                logger.info(f"Launched Chrome in app mode: {url}")
                return
            except (FileNotFoundError, OSError):
                pass

            # Try Edge
            edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
            if Path(edge_path).exists():
                subprocess.Popen([edge_path, f"--app={url}"],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
                logger.info(f"Launched Edge in app mode: {url}")
                return

            # Fall back to default browser
            webbrowser.open(url)
            logger.info(f"Launched default browser: {url}")

        elif system == "Linux":
            # Try Chrome/Chromium
            for browser in ["google-chrome", "chromium-browser", "chromium"]:
                try:
                    subprocess.Popen([browser, f"--app={url}"],
                                   stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
                    logger.info(f"Launched {browser} in app mode: {url}")
                    return
                except FileNotFoundError:
                    continue

            # Try Firefox with new-window
            try:
                subprocess.Popen(["firefox", "--new-window", url],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
                logger.info(f"Launched Firefox: {url}")
                return
            except FileNotFoundError:
                pass

            # Fall back to default browser
            webbrowser.open(url)
            logger.info(f"Launched default browser: {url}")

        else:
            # Unknown system, use default browser
            webbrowser.open(url)
            logger.info(f"Launched default browser: {url}")

    except Exception as e:
        logger.warning(f"Failed to launch browser in app mode: {e}. Falling back to default browser.")
        webbrowser.open(url)
