# Claude Code Setup Guide

Your Claude Code environment is configured with slash commands, auto-formatting, and pre-allowed permissions.

## Slash Commands

### `/commit-push`
Smart conventional commits with auto-push to current branch.

```
# Usage
/commit-push

# What it does:
1. Analyzes git diff
2. Creates conventional commit (feat/fix/chore)
3. Pushes to current branch (triggers GitHub Actions)
```

### `/test-backend`
Run backend tests with pytest.

```
# Usage
/test-backend                        # All tests
/test-backend test_quota_service.py  # Specific file
```

### `/migrate`
Database migration management.

```
# Usage
/migrate create "add user settings"  # Create new migration
/migrate up                          # Apply pending migrations
/migrate down                        # Rollback one migration
/migrate status                      # Show current status
```

### `/test-quota`
End-to-end quota system testing.

```
# Usage
/test-quota

# Tests:
- Quota consumption
- Exhaustion handling
- Graceful degradation
- Integration blocking
```

### `/test-agent`
Run agent locally in foreground mode.

```
# Usage
/test-agent

# Starts agent with:
- Foreground logging
- Flask UI on localhost:9090
- File watcher active
```

### `/create-task`
Create development tasks in Notion linked to "Building a Remarkable data pipeline" project.

```
# Usage
/create-task <task-name> [--status STATUS] [--tags TAG1,TAG2] [--description DESC]

# Examples
/create-task Fix OCR timeout issue
/create-task Add dark mode --status "Prioritized" --tags feature,ops
/create-task Implement Stripe webhooks --status "In Progress" --tags feature --description "Set up webhook endpoints for subscription events"

# Valid statuses: Backlog (default), Prioritized, In Progress, Paused
# Valid tags: development, remarkable, feature, bug, ops, marketing, learning, test
```

## Auto-Formatting Hook

After Claude edits/writes code, formatting runs automatically:

**Python files** (backend/, agent/):
- `poetry run black [file]` - Code formatting
- `poetry run ruff check --fix [file]` - Linting

**TypeScript/JavaScript** (dashboard/):
- `npx prettier --write [file]` - Code formatting

You'll see: `✓ Formatted Python: backend/app/api/quota.py`

**No action needed** - happens automatically!

## Pre-Allowed Permissions

These commands run **without permission prompts**:

**Poetry (backend/agent):**
- `poetry run pytest`, `poetry run alembic`, `poetry run uvicorn`
- `poetry run black`, `poetry run ruff`, `poetry run python`

**npm (dashboard):**
- `npm run dev`, `npm run build`, `npm install`
- `npx prettier`

**Git:**
- `git status`, `git diff`, `git log`, `git branch`
- `git add`, `git commit`, `git push`, `git pull`

**Shell:**
- `ls`, `pwd`, `find`, `grep`, `cat`, `curl`, `sqlite3`

**SSH (production):**
- `ssh deploy@167.235.74.51`

## MCP Servers (Model Context Protocol)

Your Claude Code has access to external services through MCP servers:

### Notion MCP
Access your Notion workspace for development task tracking.

**What you can do:**
- Query development tickets and task databases
- Search across your Notion workspace
- Fetch page and database contents
- Create and update pages
- Track progress on tasks

**Usage examples:**
```
> What development tasks are in my Notion workspace?
> Show me all high-priority tickets for rMirror
> Create a new page in my dev tracker for this feature
```

**Configuration:** `~/Library/Application Support/Claude/claude_desktop_config.json`

**Grant page access:**
1. Open your Notion page/database
2. Click "•••" (top right) → "Add connections"
3. Select your integration (created at notion.com/my-integrations)
4. Click "Confirm"

### Playwright MCP
Browser automation for testing and web interactions.

**What you can do:**
- Automate browser navigation
- Click elements and fill forms
- Take screenshots of web pages
- Execute JavaScript in browser context
- Test web applications (dashboard)

**Usage examples:**
```
> Navigate to localhost:3000 and take a screenshot
> Test the login flow on the dashboard
> Fill out the signup form with test data
> Click the quota upgrade button and verify navigation
```

**Testing your dashboard:**
```
> Use Playwright to test the quota exceeded modal flow
> Automate testing the Notion integration setup
> Verify the authentication redirect works
```

**Verification:** Test MCP connection with `/mcp` command in Claude Code

## File Structure

```
.claude/
├── settings.local.json     # Pre-allowed permissions
├── commands/               # Slash commands
│   ├── commit-push.md
│   ├── test-backend.md
│   ├── migrate.md
│   ├── test-quota.md
│   └── test-agent.md
└── hooks/                  # Auto-formatting
    └── PostToolUse.sh
```

## Tips

1. **Use slash commands for repetitive tasks** - saves typing and ensures consistency
2. **Let auto-formatting work** - don't worry about code style, hook handles it
3. **Permissions are shared** - works in all sessions (root, backend, dashboard, agent)
4. **Commands are documented** - Claude reads the .md files and knows how to use them

## Customization

**Add new slash command:**
1. Create `.claude/commands/my-command.md`
2. Document usage and instructions
3. Claude will auto-discover it

**Add new permission:**
1. Edit `.claude/settings.local.json`
2. Add to `"allow"` array
3. Pattern: `"Bash(command:*)"` for any arguments

**Modify hook:**
1. Edit `.claude/hooks/PostToolUse.sh`
2. Add new file extensions or formatters
3. Must be executable: `chmod +x`

---

**Created:** 2026-01-07
**Your Claude Code setup is ready!** 🚀
