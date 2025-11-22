# rMirror Mac Agent

Python background service that automatically syncs reMarkable tablet files to the rMirror Cloud.

## Features

- **Automatic File Watching** - Monitors your reMarkable Desktop app folder for changes
- **Cloud Sync** - Uploads notebooks to rMirror Cloud backend
- **Web UI** - Localhost configuration interface (http://localhost:5555)
- **System Tray** - Menu bar icon for quick access and status
- **Auto-Start** - Runs automatically on Mac startup (via launchd)

## Architecture

```
┌─────────────────────────────────────┐
│   reMarkable Desktop App Folder     │
│   (~/.local/share/remarkable/...)   │
└────────────┬────────────────────────┘
             │
             │ File System Events
             ▼
┌─────────────────────────────────────┐
│      File Watcher (watchdog)        │
│  - Monitors .rm, .metadata, .content│
│  - Filters relevant file types      │
└────────────┬────────────────────────┘
             │
             │ New/Modified Files
             ▼
┌─────────────────────────────────────┐
│         Sync Queue                  │
│  - Deduplicates events              │
│  - Batches uploads                  │
└────────────┬────────────────────────┘
             │
             │ HTTPS
             ▼
┌─────────────────────────────────────┐
│    rMirror Cloud Backend API        │
│         (FastAPI)                   │
└─────────────────────────────────────┘

         ┌───────────────┐
         │  Web UI       │◄── User Configuration
         │  (Flask)      │    http://localhost:5555
         │  Port 5555    │
         └───────────────┘

         ┌───────────────┐
         │  System Tray  │◄── Status & Quick Actions
         │  (rumps)      │
         └───────────────┘
```

## Project Structure

```
agent/
├── pyproject.toml          # Poetry dependencies
├── app/
│   ├── main.py            # Entry point
│   ├── config.py          # Configuration management
│   ├── watcher/
│   │   ├── file_watcher.py   # File watching logic
│   │   └── event_handler.py  # Event handling
│   ├── sync/
│   │   ├── cloud_sync.py     # Upload to backend API
│   │   └── queue.py          # Sync queue management
│   ├── web/
│   │   ├── app.py            # Flask web server
│   │   ├── routes.py         # API routes
│   │   └── templates/        # HTML templates
│   └── tray/
│       └── app.py            # System tray menu bar app
├── scripts/
│   ├── install.sh         # Installation script
│   └── uninstall.sh       # Uninstallation script
└── resources/
    ├── icon.png           # App icon
    └── com.rmirror.agent.plist  # launchd configuration
```

## Installation

### Prerequisites

- macOS 11.0 (Big Sur) or later
- Python 3.11 or later
- reMarkable Desktop app installed and configured
- rMirror Cloud account

### Quick Install

```bash
cd rmirror-cloud/agent
./install.sh
```

The installer will:
1. Check Python version and dependencies
2. Install the rmirror-agent package
3. Initialize configuration file
4. Set up auto-start on login (LaunchAgent)
5. Start the agent in menu bar mode

### Manual Installation

```bash
cd rmirror-cloud/agent

# Install the package
pip install --user -e .

# Initialize configuration
rmirror-agent init

# Edit the configuration file
nano ~/.config/rmirror/config.yaml

# Run the agent
rmirror-agent
```

## Configuration

Edit `~/.config/rmirror/config.yaml`:

```yaml
# rMirror Cloud API
api:
  url: "https://rmirror.cloud/v1"  # or http://localhost:8000/v1 for dev
  email: "your@email.com"
  password: "your-password"

# reMarkable Desktop app sync folder
remarkable:
  source_directory: "~/.local/share/remarkable/xochitl"
  watch_enabled: true

# Web UI
web:
  enabled: true
  port: 5555
  host: "127.0.0.1"

# System Tray
tray:
  enabled: true
  show_notifications: true

# Sync settings
sync:
  auto_sync: true
  batch_size: 10
  retry_attempts: 3
  sync_interval: 60  # seconds
```

## Usage

### Web UI

Access the web interface at http://localhost:5555

Features:
- View sync status and recent uploads
- Configure API credentials
- Set reMarkable folder location
- View sync logs
- Manually trigger sync
- Pause/resume automatic syncing

### System Tray

Click the menu bar icon for:
- **Sync Status** - See current sync state
- **Sync Now** - Trigger immediate sync
- **Open Web UI** - Launch configuration interface
- **Pause/Resume** - Control automatic syncing
- **Quit** - Stop the agent

### Command Line

```bash
# Start agent
poetry run python -m app.main

# Start with custom config
poetry run python -m app.main --config /path/to/config.yaml

# Start in foreground (debug mode)
poetry run python -m app.main --foreground

# Check status
poetry run python -m app.main --status
```

## Auto-Start on Login

The agent uses macOS launchd to start automatically on login.

### Enable Auto-Start

```bash
# Load launchd service
launchctl load ~/Library/LaunchAgents/com.rmirror.agent.plist

# Start now
launchctl start com.rmirror.agent
```

### Disable Auto-Start

```bash
# Stop agent
launchctl stop com.rmirror.agent

# Unload launchd service
launchctl unload ~/Library/LaunchAgents/com.rmirror.agent.plist
```

## Development

### Running in Development Mode

```bash
# Start with hot reload
poetry run python -m app.main --foreground --debug

# Run tests
poetry run pytest

# Type checking
poetry run mypy app/

# Linting
poetry run ruff check app/
```

### Project Dependencies

- **watchdog** - File system monitoring
- **httpx** - Async HTTP client for API calls
- **Flask** - Web UI server
- **rumps** - macOS menu bar integration
- **pyyaml** - Configuration file parsing
- **pydantic** - Configuration validation

## Troubleshooting

### Agent not starting

1. Check launchd logs: `tail -f ~/Library/Logs/rmirror-agent.log`
2. Verify Python version: `python3 --version`
3. Check service status: `launchctl list | grep rmirror`

### Files not syncing

1. Verify reMarkable folder path in config
2. Check API credentials in web UI
3. View sync logs in web UI
4. Test API connection: `curl http://localhost:5555/api/status`

### Web UI not accessible

1. Check if port 5555 is already in use: `lsof -i :5555`
2. Verify `web.enabled: true` in config
3. Check firewall settings

## Usage

### Viewing Logs

The agent logs all activity to `~/.config/rmirror/agent.log`:

```bash
# View real-time logs
tail -f ~/.config/rmirror/agent.log

# View last 50 lines
tail -n 50 ~/.config/rmirror/agent.log

# Search logs
grep "OCR extracted text" ~/.config/rmirror/agent.log
```

### Command Line Interface

```bash
# Check status
rmirror-agent status

# Run in foreground (for debugging)
rmirror-agent --foreground

# Run with debug logging
rmirror-agent --debug

# Show help
rmirror-agent --help
```

## Uninstallation

```bash
cd rmirror-cloud/agent
./uninstall.sh
```

This will:
1. Stop and remove the LaunchAgent
2. Uninstall the Python package
3. Configuration files in `~/.config/rmirror` are preserved (remove manually if desired)

## License

AGPL-3.0 - See LICENSE file

## Support

- Issues: https://github.com/gottino/rmirror-cloud/issues
- Discussions: https://github.com/gottino/rmirror-cloud/discussions
