#!/bin/bash
set -e

# rMirror Agent Installation Script for macOS
# This script installs the rMirror Agent and sets it up to run automatically

echo "🚀 Installing rMirror Agent..."
echo ""

# Check if we're on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "❌ Error: This installer is only for macOS"
    exit 1
fi

# Check if Python 3.11+ is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed"
    echo "Please install Python 3.11 or later from https://www.python.org/downloads/"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
REQUIRED_VERSION="3.11"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "❌ Error: Python $REQUIRED_VERSION or later is required (found $PYTHON_VERSION)"
    exit 1
fi

echo "✓ Python $PYTHON_VERSION found"

# Check for pip
if ! python3 -m pip --version &> /dev/null; then
    echo "❌ Error: pip is not installed"
    exit 1
fi

echo "✓ pip found"

# Install the package
echo ""
echo "📦 Installing rmirror-agent package..."

# Option 1: Install from PyPI (when published)
# python3 -m pip install --user rmirror-agent

# Option 2: Install from local directory (for development)
python3 -m pip install --user -e .

echo "✓ Package installed"

# Create config directory
CONFIG_DIR="$HOME/.config/rmirror"
mkdir -p "$CONFIG_DIR"

# Initialize config if it doesn't exist
if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
    echo ""
    echo "📝 Creating default configuration..."
    rmirror-agent init
    echo ""
    echo "⚠️  Please edit the configuration file to add your rMirror Cloud credentials:"
    echo "   $CONFIG_DIR/config.yaml"
    echo ""
    read -p "Press Enter after you've configured your credentials..."
fi

# Set up LaunchAgent for auto-start
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_FILE="$PLIST_DIR/cloud.rmirror.agent.plist"

mkdir -p "$PLIST_DIR"

echo ""
echo "🔧 Setting up auto-start..."

# Get the path to the installed rmirror-agent command
AGENT_PATH=$(which rmirror-agent)

# Create LaunchAgent plist
cat > "$PLIST_FILE" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>cloud.rmirror.agent</string>

    <key>ProgramArguments</key>
    <array>
        <string>$AGENT_PATH</string>
        <string>--config</string>
        <string>$CONFIG_DIR/config.yaml</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>$CONFIG_DIR/stdout.log</string>

    <key>StandardErrorPath</key>
    <string>$CONFIG_DIR/stderr.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin</string>
    </dict>
</dict>
</plist>
EOF

echo "✓ LaunchAgent created: $PLIST_FILE"

# Load the LaunchAgent
launchctl unload "$PLIST_FILE" 2>/dev/null || true
launchctl load "$PLIST_FILE"

echo "✓ LaunchAgent loaded"

echo ""
echo "✅ Installation complete!"
echo ""
echo "The rMirror Agent is now running in your menu bar and will start automatically on login."
echo ""
echo "Useful commands:"
echo "  rmirror-agent status          - Check agent status"
echo "  rmirror-agent --foreground    - Run in foreground mode (for debugging)"
echo "  rmirror-agent --help          - Show all commands"
echo ""
echo "Logs are written to: $CONFIG_DIR/agent.log"
echo ""
