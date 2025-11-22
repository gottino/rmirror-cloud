#!/bin/bash
set -e

# rMirror Agent Uninstallation Script for macOS

echo "🗑️  Uninstalling rMirror Agent..."
echo ""

# Stop and unload LaunchAgent
PLIST_FILE="$HOME/Library/LaunchAgents/cloud.rmirror.agent.plist"

if [ -f "$PLIST_FILE" ]; then
    echo "Stopping agent..."
    launchctl unload "$PLIST_FILE" 2>/dev/null || true
    rm "$PLIST_FILE"
    echo "✓ LaunchAgent removed"
fi

# Uninstall the package
echo "Removing package..."
python3 -m pip uninstall -y rmirror-agent || true
echo "✓ Package removed"

echo ""
echo "✅ Uninstallation complete!"
echo ""
echo "Note: Configuration files in ~/.config/rmirror were not removed."
echo "To remove them: rm -rf ~/.config/rmirror"
echo ""
