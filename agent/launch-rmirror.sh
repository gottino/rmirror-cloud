#!/bin/bash
# rMirror Agent Launcher - macOS/Linux
# This script launches rMirror Agent with auto-browser in app mode

# Change to the agent directory
cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Launch the agent
# The agent will automatically:
# - Start the web server on port 5555
# - Open Chrome/Chromium in app mode (no browser bars)
# - Show a menu bar icon for easy access
rmirror-agent

# If the command above doesn't work, try:
# python -m app.main
