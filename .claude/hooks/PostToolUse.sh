#!/bin/bash

# PostToolUse hook - Auto-format code after Claude edits
# Runs after Edit, Write, or NotebookEdit tools

# Only run for Edit and Write tools
if [[ "$TOOL_NAME" != "Edit" && "$TOOL_NAME" != "Write" ]]; then
  exit 0
fi

FILE_PATH="$TOOL_INPUT_file_path"

# Check if file exists
if [[ ! -f "$FILE_PATH" ]]; then
  exit 0
fi

# Get file extension
EXT="${FILE_PATH##*.}"

# Format Python files
if [[ "$EXT" == "py" ]]; then
  # Check if we're in backend or agent directory
  if [[ "$FILE_PATH" == *"/backend/"* ]] || [[ "$FILE_PATH" == *"/agent/"* ]]; then
    DIR=$(echo "$FILE_PATH" | grep -oE '(backend|agent)')
    cd "$DIR" 2>/dev/null || exit 0

    # Run black and ruff
    poetry run black "$FILE_PATH" 2>/dev/null
    poetry run ruff check --fix "$FILE_PATH" 2>/dev/null

    echo "✓ Formatted Python: $FILE_PATH"
  fi
fi

# Format TypeScript/JavaScript files
if [[ "$EXT" == "ts" || "$EXT" == "tsx" || "$EXT" == "js" || "$EXT" == "jsx" ]]; then
  # Check if we're in dashboard directory
  if [[ "$FILE_PATH" == *"/dashboard/"* ]]; then
    cd dashboard 2>/dev/null || exit 0

    # Run prettier
    npx prettier --write "$FILE_PATH" 2>/dev/null

    echo "✓ Formatted TypeScript: $FILE_PATH"
  fi
fi

exit 0
