@echo off
REM rMirror Agent Launcher - Windows
REM This script launches rMirror Agent with auto-browser in app mode

cd /d "%~dp0"

REM Activate virtual environment if it exists
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

REM Launch the agent
REM The agent will automatically:
REM - Start the web server on port 5555
REM - Open Chrome/Edge in app mode (no browser bars)
REM - Show a system tray icon for easy access
rmirror-agent

REM If the command above doesn't work, try:
REM python -m app.main

pause
