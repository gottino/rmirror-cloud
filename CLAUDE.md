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
- Each `.claudecontext` holds the domain-specific details

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

# Web UI accessible at localhost:5555
```

### Dashboard (Next.js)

```bash
cd dashboard

npm install
npm run dev          # Development server (port 3000)
npm run lint         # next lint
npm test             # vitest
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

`docs/archive/` holds historical documents (old architecture, plans, test reports). They describe systems that no longer exist and may be wrong; trust the code, not those files.

### Key Architectural Patterns

**Background Sync Worker**: Asyncio-based worker (`app/services/sync_worker.py`, started from the FastAPI lifespan) polls the `sync_queue` table every 5 seconds. It shares one event loop with the request handlers, so blocking calls (Gemini SDK, boto3, Notion SDK, rsvg-convert) must run off the loop via `run_off_loop` from `app/utils/concurrency.py`. Close SQLAlchemy sessions in finally blocks. Each uvicorn process runs its own worker; queue rows are claimed with `FOR UPDATE SKIP LOCKED`.

**Database-Driven Deduplication**: `sync_records` table is source of truth. Uses `page_uuid` (reMarkable's unique ID) for deduplication, not content hashes. Clean Notion titles without hashes.

**Quota System**: Separate `subscriptions` and `quota_usage` tables (`app/services/quota_service.py`). Free tier: 30 pages/month, beta users on the free tier: 200, pro: 500, enterprise: unlimited. Enforced at backend before OCR. Graceful degradation: accepts uploads when exhausted, skips OCR, pages set to `PENDING_QUOTA` status (capped at 100 pending pages per user, then uploads get HTTP 429).

**Metadata vs Content Sync**: Two sync types - `NOTEBOOK` (full content with OCR) and `NOTEBOOK_METADATA` (lightweight, updates only Notion properties). Content syncs go through `sync_queue` (`item_type` `page_text` or `todo`). Metadata sync is not a queue item: `POST /processing/metadata/update` builds a `NOTEBOOK_METADATA` item and syncs it inline through `UnifiedSyncManager`, skipped when quota is exhausted. Metadata syncs 50-100x faster (~100ms vs ~5s).

**Graceful Degradation**: When quota exhausted, uploads accepted, PDFs generated, OCR deferred. Pages show "OCR Pending" in dashboard. Retroactive processing when quota resets (newest pages first, `app/jobs/process_pending_pages.py`). The sync worker does this (`_process_pending_quota_pages`, a few users/pages per poll, one worker per user via a Postgres advisory lock); request code such as `reset_quota()` must never spawn background tasks.

## Database Schema

### Core Tables

**users**: `email`, `clerk_user_id` (login is Clerk only; password endpoints were removed), `is_beta_user`, onboarding and legal-acceptance fields, `created_at`

**subscriptions**: `user_id`, `tier` (free/pro/enterprise), `status`, `current_period_start`, `current_period_end`, `stripe_customer_id` (nullable, Phase 2)

**quota_usage**: `user_id`, `quota_type` (`ocr`), `limit` (-1 = unlimited), `used`, `reset_at`, `period_start`

**notebooks**: `user_id`, `notebook_uuid`, `visible_name`, `parent_uuid` (folder hierarchy), `full_path`, `document_type`, `deleted`

**pages**: `notebook_id`, `page_uuid` (nullable, NOT unique), `ocr_text`, `ocr_status` (not_synced/pending/processing/completed/failed/skipped/pending_quota), `file_hash`, `s3_key`, `pdf_s3_key`

**notebook_pages**: `notebook_id`, `page_id`, `page_number` (order of pages in a notebook; unique on (`notebook_id`, `page_id`) and (`notebook_id`, `page_number`))

**sync_queue**: `user_id`, `item_type` (`page_text`/`todo`), `item_id`, `content_hash`, `page_uuid`, `target_name`, `status`, `priority` (1-10, lower runs first, default 5), `scheduled_at`

**sync_records**: `user_id`, `page_uuid` (unique per target and user), `external_id` (Notion block ID), `content_hash`, `target_name` (notion/obsidian/todoist/notion-todos), `item_type`, `status`, `synced_at`

**integration_configs**: `user_id`, `target_name`, `config_encrypted`, `is_enabled`, `api_key_hash` (Obsidian), `last_synced_at`; unique on (`user_id`, `target_name`)

### Important Constraints

- `sync_records`: UNIQUE on (`page_uuid`, `target_name`, `user_id`) - prevents duplicates
- `subscriptions`: UNIQUE on `user_id` - one subscription per user
- `quota_usage`: UNIQUE index on (`user_id`, `quota_type`) (`idx_quota_user_type`, created in migration `2d86de0d1c3c`)

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
2. Use async/await for route handlers; blocking client calls go through `run_off_loop`
3. Check quota with `quota_service` (`app/services/quota_service.py`) if endpoint consumes resources
4. Add to OpenAPI docs with proper types
5. Test locally before committing

### Adding Notion Sync Feature

1. Database is source of truth (`sync_records` table)
2. Use `page_uuid` for deduplication (NOT `content_hash`)
3. Handle archived blocks: catch "Can't edit block that is archived"
4. Upsert pattern: query by page identifier, update if exists
5. Reference: `backend/app/integrations/notion_sync.py` and `backend/app/services/sync_worker.py`

### Handling Quota

- Check quota: `quota_service.check_quota(db, user_id, quota_type, amount)` (returns a bool)
- Consume quota: `quota_service.consume_quota(db, user_id, quota_type, amount)` (after success; raises `QuotaExceededError`)
- Uploads are never rejected for quota: OCR is skipped and the page becomes `PENDING_QUOTA`. HTTP 402 with quota details in the error body is returned for features that need quota, such as notebook export
- Block OCR AND integration syncs when quota exhausted
- Frontend shows `QuotaExceededModal` on 402 errors

### Testing Agent + Backend Integration

1. Start backend: `cd backend && poetry run uvicorn app.main:app --reload`
2. Start agent: `cd agent && poetry run python -m app.main --foreground --debug`
3. Copy `.rm` files into the reMarkable Desktop sync folder (`remarkable.source_directory` in the agent config)
4. Watch agent logs for upload activity
5. Check backend logs for processing
6. Verify database: `sqlite3 backend/rmirror.db` or `psql` for production

## Critical Gotchas

### Backend

- **SQLAlchemy sessions**: MUST close in finally blocks (especially in background workers)
- **Notion API 2025-09-03**: Requires data source API for adding properties
- **Archived blocks**: Catch "Can't edit block that is archived" - treat as deleted
- **Quota enforcement**: Check before OCR, consume after success (not before upload)
- **Duplicate `page_uuid`**: `pages.page_uuid` has no unique constraint; never assume one row per UUID
- **Sync deduplication**: Query by `page_uuid`, not `content_hash`
- **Event loop**: blocking SDK calls inside `async def` stall every request and the sync worker; wrap them with `run_off_loop` (`app/utils/concurrency.py`)
- **Auth**: Clerk only. `/auth/login` and the other password endpoints were removed; the only token endpoint is `POST /auth/agent-token`
- **OCR**: Google Gemini (`ocr_model`, default `gemini-2.5-flash`, key `GOOGLE_AI_API_KEY`)
- **Poetry required**: ALWAYS use `poetry run` for alembic, pytest, uvicorn

### Agent

- **Thread safety**: rumps runs on main thread, Flask/watchdog in background threads
- **macOS permissions**: Needs Full Disk Access to read reMarkable folder
- **Token storage**: Uses system keychain (keyring library)
- **Config location**: `~/.config/rmirror/config.yaml` (also read: `~/.rmirror/config.yaml`, `./config.yaml`; override with `--config` or `RMIRROR_CONFIG_PATH`). Logs go to `~/.config/rmirror/agent.log`
- **reMarkable files**: `.rm` files are binary and uploaded as-is (the backend converts them, `backend/app/core/rm_converter.py`); the agent only reads the `.metadata` and `.content` JSON files (`app/remarkable/metadata_scanner.py`)
- **Auth**: web UI sign-in redirects to the dashboard `/agent` bridge page (production Clerk keys) or renders `app/web/templates/auth_bridge.html` (dev keys), which exchanges the Clerk session for a 30-day agent JWT

### Dashboard

- **Server vs Client Components**: Default is Server Components (add `'use client'` for hooks)
- **Clerk auth on Server**: Use `await auth()` from `@clerk/nextjs/server` (Clerk v6); `middleware.ts` uses `clerkMiddleware` from the same module
- **API URL**: Must use `process.env.NEXT_PUBLIC_API_URL` (prefixed with NEXT_PUBLIC_; it already includes `/api/v1`, e.g. `http://localhost:8000/v1` locally)
- **Protected routes**: See `middleware.ts` - everything except `/`, `/sign-in`, `/sign-up`, `/legal` and `/agent` requires sign-in
- **Quota errors**: Handle 402 status code, show `QuotaExceededModal`

## Deployment

**Production**: Hetzner VPS (<server-ip>) via GitHub Actions

```bash
# SSH access
ssh deploy@<server-ip>

# Backend (systemd): `rmirror` = production, `rmirror-staging` = staging
sudo systemctl status rmirror

# Logs (the backend logs JSON to stdout, so they are in journald)
sudo journalctl -u rmirror -f

# Dashboard (pm2): `rmirror-dashboard` (port 3000) = production,
# `rmirror-dashboard-staging` (port 3100) = staging
pm2 status

# Database access (database `rmirror`; staging uses `rmirror_staging`)
sudo -u postgres psql rmirror

# Production .env lives next to the code
ls /var/www/rmirror-cloud/backend/.env   # staging: /var/www/rmirror-staging/backend/.env
```

**CI/CD**: Push to `main` deploys to **staging** (`staging.rmirror.io`, `deploy-staging.yml`, runs CI first and Playwright E2E afterwards). Production is deployed by running the "Deploy to Production" workflow by hand (`deploy-production.yml`; it requires green CI and a healthy staging, and ends in `backend/scripts/deploy.sh`). Staging and production share one server.

**Dashboard builds run in GitHub Actions, never on the server**: `npm ci` + `next build` there ran the 4 GB box out of memory (2026-10-21). The deploy workflows build a Next.js standalone server (`NEXT_OUTPUT=standalone`), upload it, and `dashboard/deploy/install-release.sh` installs it under pm2 from `~/rmirror-releases/`, rolling back if it doesn't come up.

## Design System

**Moleskine-inspired warm palette**:
- Brand color (terracotta): `#c85a54`
- Warm charcoal: `#2c2c2c`
- Sage green: `#9bb7a2`
- Amber gold: `#e8b65b`
- Cream: `#f5f5dc`

All UI components (emails, dashboard, agent) use this consistent design system.

## Current Status (November 2026)

**Completed**:
- OCR switched to Google Gemini 2.5 Flash (was Claude Haiku)
- OCR benchmark tool (5 models, 3 providers, `backend/benchmark/`)
- Obsidian integration (API key auth, content hash sync)
- Todoist integration and Notion todo sync
- Agent auth bridge (dashboard `/agent` page, local `auth_bridge.html` for dev keys)
- Clerk-only login (password endpoints removed, PR #34)
- Per-notebook deletion with cascade cleanup
- Beta user quota (200 pages/month)
- Legal compliance (terms/privacy acceptance)
- Umami analytics (self-hosted, cookie-less)
- Onboarding checklist + email drip campaign
- Agent v1.6.0 with Intel build support, update check against `version.json`
- Quota system Phase 1 (30 pages/month free tier)
- Graceful degradation (accept uploads when quota exhausted)
- Retroactive OCR processing (newest pages first), run by the sync worker (PR #50)
- Blocking calls moved off the event loop (`app/utils/concurrency.py`)
- Email notifications (90% warning, 100% exceeded)
- Page limit control for initial sync
- Agent quota display with color-coded status
- Dashboard quota UI with upgrade CTAs, search, notebook export (Markdown/PDF)
- Metadata-only sync (50-100x faster)
- Database-driven deduplication with `page_uuid`
- Staging environment, deployed on push to `main`; production by manual workflow
- Dashboard built in CI as a standalone server, installed under pm2
- Production deployment on Hetzner

**In Progress**:
- None currently

**Planned**:
- Phase 2: Stripe integration for paid tiers (subscription columns exist, unused)
- Readwise integration (not started; no code yet)
- Dashboard improvements
