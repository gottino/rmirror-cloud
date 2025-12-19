# rMirror Agent - Standalone App Mode

The rMirror Agent can run as a standalone desktop application with minimal browser chrome, giving it a native app feel while keeping all the benefits of the web-based UI.

## Features

- **Auto-Launch Browser**: The agent automatically opens your browser when it starts
- **App Mode**: Uses Chrome/Edge/Chromium `--app` flag to hide browser toolbars and make it feel like a native app
- **System Tray**: Menu bar icon (macOS) or system tray (Windows/Linux) for quick access
- **Cross-Platform**: Works on macOS, Windows, and Linux

## Quick Start

### macOS/Linux
```bash
./launch-rmirror.sh
```

### Windows
```
launch-rmirror.bat
```

Or just run the agent directly:
```bash
rmirror-agent
```

The agent will:
1. Start the web server on `http://localhost:5555`
2. Automatically open Chrome/Edge in app mode (no browser bars)
3. Show a system tray/menu bar icon for easy access

## Configuration

You can customize the standalone app behavior in your `~/.config/rmirror/config.yaml`:

```yaml
web:
  enabled: true
  port: 5555
  host: 127.0.0.1
  auto_launch_browser: true    # Auto-open browser on startup (default: true)
  app_mode: true               # Use browser app mode (default: true)

tray:
  enabled: true                # Show system tray icon (default: true)
  show_notifications: true     # Desktop notifications (default: true)
```

### Disable Auto-Launch

If you prefer to manually open the browser:

```yaml
web:
  auto_launch_browser: false
```

### Disable App Mode

If you prefer the full browser UI:

```yaml
web:
  app_mode: false
```

### Disable System Tray

To run in foreground mode without tray icon:

```bash
rmirror-agent --foreground
```

Or in the config:

```yaml
tray:
  enabled: false
```

## Environment Variables

You can also configure via environment variables:

```bash
export RMIRROR_WEB_AUTO_LAUNCH_BROWSER=false
export RMIRROR_WEB_APP_MODE=false
export RMIRROR_WEB_PORT=8080
rmirror-agent
```

## Browser Detection

The agent tries browsers in this order:

### macOS
1. Google Chrome (app mode)
2. Default browser (standard mode)

### Windows
1. Google Chrome (app mode)
2. Microsoft Edge (app mode)
3. Default browser (standard mode)

### Linux
1. Google Chrome / Chromium (app mode)
2. Firefox (new window)
3. Default browser (standard mode)

## System Tray Features

Click the menu bar/system tray icon to:

- **View Status**: See if agent is connected, authenticated, watching files
- **Open Web UI**: Launch the web interface in app mode
- **Settings**: Access configuration (same as "Open Web UI")
- **Quit**: Stop the agent cleanly

## Packaging as Native Installer

The current setup already provides a great standalone experience. For even more polish, you can:

1. **macOS**: Use the existing `build_macos.sh` script to create a `.app` bundle
   - The .app will have an icon, appear in Applications folder
   - Double-click to launch (no terminal window)

2. **Windows**: Use PyInstaller to create `.exe`
   - Add to Start Menu
   - Run on startup

3. **Linux**: Create `.desktop` file for application menu
   - Add icon to launcher
   - System autostart integration

See `build_macos.sh` for macOS packaging example.

## Troubleshooting

### Browser doesn't open in app mode

- **Cause**: Chrome/Edge not installed or not in standard location
- **Solution**: Install Chrome, or disable app mode in config

### Multiple browser windows open

- **Cause**: Clicking tray "Open Web UI" when browser already open
- **Solution**: This is normal - app mode windows are independent

### Want to use a different browser

- **Solution**: Set `app_mode: false` in config, and your system default browser will be used

### Port 5555 already in use

- **Solution**: Change the port in config:
  ```yaml
  web:
    port: 8080
  ```

## Technical Details

### How App Mode Works

When `app_mode: true`, the agent launches Chrome/Edge with the `--app=<url>` flag:

```bash
# macOS
/Applications/Google Chrome.app/Contents/MacOS/Google Chrome --app=http://localhost:5555

# Windows
"C:\Program Files\Google\Chrome\Application\chrome.exe" --app=http://localhost:5555

# Linux
google-chrome --app=http://localhost:5555
```

This creates a minimal window with:
- No address bar
- No bookmarks bar
- No browser tabs
- No extensions UI
- Just your web app content

Perfect for making web apps feel native!

### Architecture

The agent runs three components:

1. **Flask Web Server** (background thread): Serves the UI on port 5555
2. **File Watcher** (async task): Monitors reMarkable folder for changes
3. **System Tray** (main thread): Provides menu bar/tray icon

On startup with `auto_launch_browser: true`:
1. Web server starts
2. Browser launches in app mode automatically
3. User sees the web UI in a minimal, app-like window

## Next Steps

- Add custom app icon
- Create native installers (`.pkg` for macOS, `.msi` for Windows, `.deb` for Linux)
- Add desktop notifications for sync events
- Consider Electron wrapper if you need deeper OS integration
