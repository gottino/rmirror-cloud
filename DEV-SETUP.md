# Development Setup

## Claude Code Multi-Instance Workflow

This project uses a multi-instance Claude Code workflow for efficient development.

### Quick Start

```bash
# 1. Run setup script (one-time, 2 minutes)
./scripts/setup_dev_context.sh

# 2. Read the workflow documentation
cat dev-context/README.md
```

### What This Does

- Creates `dev-context/` as a separate git repository (like `security/`)
- Contains architectural decisions, development workflow, and current state
- Enables focused Claude Code sessions per domain (backend, frontend, etc.)
- Prevents context limits and improves session efficiency

### Files Created

**Main repo** (committed):
- `backend/.claudecontext` - Backend development context
- `.claude-workflow-card.txt` - Print-friendly quick reference
- `scripts/setup_dev_context.sh` - Setup automation

**Dev context** (separate repo, gitignored):
- `dev-context/README.md` - Start here for full documentation
- `dev-context/GETTING_STARTED.md` - Quick start guide
- `dev-context/WORKFLOW.md` - Complete workflow documentation
- `dev-context/architecture/` - System design docs
- `dev-context/decisions/` - Technical decisions log
- `dev-context/state/` - Current work state

### Daily Workflow

```bash
# Check current state
cat dev-context/state/current-state.md

# Start focused session
cd backend  # or dashboard, or root
# Open Claude Code
# Say: "Read .claudecontext, task: [specific task]"

# End session
vim dev-context/state/current-state.md  # Update progress
cd dev-context && git commit -am "state: update"
cd .. && git commit -am "feat: description"
```

### Benefits

- ✅ Never hit Claude Code context limits
- ✅ Faster session startup (focused context)
- ✅ Better documentation (decisions tracked)
- ✅ Easy to resume work after breaks
- ✅ Cleaner git history (domain-focused commits)

---

**Next**: Run `./scripts/setup_dev_context.sh` and read `dev-context/README.md`
