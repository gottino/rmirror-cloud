# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**rMirror Cloud** is an open-source cloud service for reMarkable tablet integration with AI-powered handwriting recognition. The system consists of three main components:

- **Backend (FastAPI)**: REST API, OCR processing, integration syncs, quota management
- **Agent (Python)**: macOS background service that monitors reMarkable sync folder and uploads to backend
- **Dashboard (Next.js)**: Web interface for viewing notebooks and managing integrations

## Multi-Instance Workflow (Important!)

This repository uses **domain-specific sessions** for focused, efficient work:

### Start sessions in specific folders:

```bash
# Backend work
cd backend
# Open Claude Code here → reads backend/.claudecontext automatically

# Dashboard work (separate session)
cd dashboard
# Open Claude Code here → reads dashboard/.claudecontext automatically

# Agent work (separate session)
cd agent
# Open Claude Code here → reads agent/.claudecontext automatically
```

**Why separate sessions?**
- Focused context (only loads what you need)
- Faster responses (less context to process)
- Cleaner history (backend changes don't pollute dashboard session)
- Each `.claudecontext` is 150-170 lines of domain-specific details

### When to use root session (this file):

Start from repository root when doing:
- Initial orientation (understanding the whole system)
- Cross-cutting changes (affects multiple components)
- Infrastructure/deployment work
- Documentation updates

### When to use domain sessions:

- **backend/**: API endpoints, database migrations, OCR processing, Notion sync, quota logic
- **dashboard/**: UI components, pages, Clerk auth, quota display
- **agent/**: File watching, cloud sync, Flask web UI, macOS menu bar

**Don't** change directories during a session - open a new session in the target folder instead.

## Development Commands

### Backend (FastAPI)

```bash
cd backend

# Always use Poetry for all commands
poetry install
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Database migrations (ALWAYS use poetry run)
poetry run alembic upgrade head                    # Apply migrations
poetry run alembic revision -m "description"       # Create new migration
poetry run alembic downgrade -1                    # Rollback one migration

# Testing
poetry run pytest                                  # Run all tests
poetry run pytest tests/test_specific.py           # Run specific test file
poetry run pytest -v                               # Verbose output
```

### Agent (Python)

```bash
cd agent

poetry install

# Development (foreground mode with logs)
poetry run python -m app.main --foreground --debug

# Build macOS .app bundle
./build_macos.sh

# Web UI accessible at localhost:9090
```

### Dashboard (Next.js)

```bash
cd dashboard

npm install
npm run dev          # Development server (port 3000)
npm run build        # Production build
npm run start        # Production server
```

### Local Development Setup

Backend uses **SQLite** for local development (no PostgreSQL setup needed). Production uses PostgreSQL on Hetzner.

```bash
# Terminal 1: Backend
cd backend
poetry install
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Dashboard (optional)
cd dashboard
npm install
npm run dev

# Terminal 3: Agent (optional, for testing uploads)
cd agent
poetry install
poetry run python -m app.main --foreground --debug
```

Database file: `backend/rmirror.db` (SQLite, gitignored)

## Architecture Overview

### Multi-Instance Claude Code Workflow

This project uses domain-specific `.claudecontext` files for focused sessions:

- **Backend sessions**: `cd backend` - Read `backend/.claudecontext` for backend-specific context
- **Dashboard sessions**: `cd dashboard` - Read `dashboard/.claudecontext` for frontend context
- **Agent sessions**: `cd agent` - Read `agent/.claudecontext` for agent context

**Private development context** stored in `dev-context/` (separate git repo, gitignored):
- `dev-context/architecture/` - System design documents
- `dev-context/decisions/technical-decisions.md` - ADR-style decision log
- `dev-context/state/current-state.md` - Current work tracker

### Key Architectural Patterns

**Background Sync Worker**: Asyncio-based worker polls `sync_queue` table every 5 seconds. Must use async/await throughout and close SQLAlchemy sessions in finally blocks.

**Database-Driven Deduplication**: `sync_records` table is source of truth. Uses `page_uuid` (reMarkable's unique ID) for deduplication, not content hashes. Clean Notion titles without hashes.

**Quota System**: Separate `subscriptions` and `quota_usage` tables. Free tier: 30 pages/month. Enforced at backend before OCR. Graceful degradation: accepts uploads when exhausted, skips OCR, pages set to `PENDING_QUOTA` status.

**Metadata vs Content Sync**: Two sync types - `NOTEBOOK` (full content with OCR) and `NOTEBOOK_METADATA` (lightweight, updates only Notion properties). Metadata syncs 50-100x faster (~100ms vs ~5s).

**Graceful Degradation**: When quota exhausted, uploads accepted, PDFs generated, OCR deferred. Pages show "OCR Pending" in dashboard. Retroactive processing when quota resets (newest pages first).

## Database Schema

### Core Tables

**users**: Authentication, email, created_at

**subscriptions**: `user_id`, `tier` (free/pro/enterprise), `status`, `current_period_start`, `current_period_end`, `stripe_customer_id` (nullable, Phase 2)

**quota_usage**: `user_id`, `quota_type` (ocr_pages), `limit`, `used`, `reset_at`, `period_start`

**notebooks**: `user_id`, `notebook_uuid`, `visible_name`, `parent_uuid` (folder hierarchy)

**pages**: `notebook_id`, `page_uuid` (unique), `page_number`, `ocr_text`, `ocr_status` (pending/completed/failed/pending_quota), `content_hash`, `pdf_s3_key`

**sync_queue**: `user_id`, `item_type` (notebook/notebook_metadata), `item_id`, `content_hash`, `status`, `priority`

**sync_records**: `user_id`, `page_uuid` (unique per target), `external_id` (Notion block ID), `content_hash`, `target_name` (notion/readwise), `synced_at`

**integration_configs**: `user_id`, `service_name`, `credentials_encrypted`, `settings`, `enabled`

### Important Constraints

- `sync_records`: UNIQUE on (`page_uuid`, `target_name`, `user_id`) - prevents duplicates
- `subscriptions`: UNIQUE on `user_id` - one subscription per user
- `quota_usage`: Composite index on (`user_id`, `quota_type`) for fast lookups

## Common Workflows

### Making Database Changes

1. Create migration: `cd backend && poetry run alembic revision -m "description"`
2. Edit migration file in `backend/alembic/versions/`
3. Test on local SQLite: `poetry run alembic upgrade head`
4. Update models in `backend/app/models/`
5. Test production PostgreSQL before deploying
6. **CRITICAL**: Always use `poetry run alembic` (never bare `alembic`)

### Adding Backend API Endpoint

1. Add route in `backend/app/api/[resource].py`
2. Use async/await for all route handlers
3. Check quota with `QuotaService` if endpoint consumes resources
4. Add to OpenAPI docs with proper types
5. Test locally before committing

### Adding Notion Sync Feature

1. Database is source of truth (`sync_records` table)
2. Use `page_uuid` for deduplication (NOT `content_hash`)
3. Handle archived blocks: catch "Can't edit block that is archived"
4. Upsert pattern: query by page identifier, update if exists
5. Reference: `rm-int-src/integrations/notion_incremental.py` (working implementation)

### Handling Quota

- Check quota: `quota_service.check_quota(user_id, quota_type, amount)`
- Consume quota: `quota_service.consume_quota(user_id, quota_type, amount)` (after success)
- Return HTTP 402 when exhausted with quota details in error body
- Block OCR AND integration syncs when quota exhausted
- Frontend shows `QuotaExceededModal` on 402 errors

### Testing Agent + Backend Integration

1. Start backend: `cd backend && poetry run uvicorn app.main:app --reload`
2. Start agent: `cd agent && poetry run python -m app.main --foreground --debug`
3. Copy `.rm` files to reMarkable sync folder
4. Watch agent logs for upload activity
5. Check backend logs for processing
6. Verify database: `sqlite3 backend/rmirror.db` or `psql` for production

## Critical Gotchas

### Backend

- **SQLAlchemy sessions**: MUST close in finally blocks (especially in background workers)
- **Notion API 2025-09-03**: Requires data source API for adding properties
- **Archived blocks**: Catch "Can't edit block that is archived" - treat as deleted
- **Quota enforcement**: Check before OCR, consume after success (not before upload)
- **Sync deduplication**: Query by `page_uuid`, not `content_hash`
- **Poetry required**: ALWAYS use `poetry run` for alembic, pytest, uvicorn

### Agent

- **Thread safety**: rumps runs on main thread, Flask/watchdog in background threads
- **macOS permissions**: Needs Full Disk Access to read reMarkable folder
- **Token storage**: Uses system keychain (keyring library)
- **Config location**: Always `~/.rmirror/config.yaml`
- **reMarkable files**: `.rm` files are binary (use `app/remarkable/parser.py`)

### Dashboard

- **Server vs Client Components**: Default is Server Components (add `'use client'` for hooks)
- **Clerk auth on Server**: Use `auth()` from `@clerk/nextjs`
- **API URL**: Must use `process.env.NEXT_PUBLIC_API_URL` (prefixed with NEXT_PUBLIC_)
- **Protected routes**: See `middleware.ts` - most routes protected by default
- **Quota errors**: Handle 402 status code, show `QuotaExceededModal`

## Deployment

**Production**: Hetzner VPS (167.235.74.51) via GitHub Actions

```bash
# SSH access
ssh deploy@167.235.74.51

# Check backend service
systemctl status rmirror-backend

# View logs
tail -f /var/log/rmirror/backend.log

# Database access
psql -U rmirror -d rmirror

# Get production .env
cat /var/www/rmirror-cloud/backend/.env | grep DATABASE_URL
```

**CI/CD**: Push to `main` branch triggers GitHub Actions deployment

## Design System

**Moleskine-inspired warm palette**:
- Brand color (terracotta): `#c85a54`
- Warm charcoal: `#2c2c2c`
- Sage green: `#9bb7a2`
- Amber gold: `#e8b65b`
- Cream: `#f5f5dc`

All UI components (emails, dashboard, agent) use this consistent design system.

## Current Status (January 2026)

**Completed**:
- Quota system Phase 1 (30 pages/month free tier)
- Graceful degradation (accept uploads when quota exhausted)
- Retroactive OCR processing (newest pages first)
- Email notifications (90% warning, 100% exceeded)
- Page limit control for initial sync
- Agent quota display with color-coded status
- Dashboard quota UI with upgrade CTAs
- Metadata-only sync (50-100x faster)
- Database-driven deduplication with `page_uuid`
- Production deployment on Hetzner

**In Progress**:
- None currently

**Planned**:
- Phase 2: Stripe integration for paid tiers
- Readwise integration
- Dashboard improvements
