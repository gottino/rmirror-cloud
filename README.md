# rMirror Cloud

**Open source cloud service for reMarkable tablet integration.**

Mirror your reMarkable notes to the cloud with AI-powered handwriting recognition. Self-host or use our managed service.

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135+-green.svg)](https://fastapi.tiangolo.com)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black)](https://nextjs.org)

---

## ✨ Features

- 🔄 **Automatic Sync** - Lightweight macOS agent monitors your reMarkable and syncs to the cloud
- 🤖 **AI Handwriting Recognition** - Gemini 2.5 Flash Vision for superior accuracy
- 🔌 **Notion Integration** - Automatic sync to Notion databases with OAuth authentication
- 📓 **Obsidian Integration** - Sync notebooks to your Obsidian vault via plugin
- 🌐 **Web Dashboard** - Browse, search, and manage notebooks from anywhere
- 📊 **Quota Management** - Beta tier with 200 pages/month, graceful degradation when exhausted
- ⚡ **Smart Sync** - Metadata-only updates 50-100x faster than full content sync
- 🔓 **Fully Open Source** - AGPL-3.0 licensed, audit the code yourself
- 🛡️ **Privacy First** - Self-host option for complete control

---

## 🚀 Quick Start

### Option 1: Managed Cloud Service

**Currently in beta** - Join the waitlist at [rmirror.io](https://rmirror.io)

**Beta tier:** 200 pages/month OCR processing
**Pro (planned):** Unlimited processing + priority support

### Option 2: Self-Hosting

**Requirements:** Python 3.11+, Node.js 18+, PostgreSQL (or SQLite for dev)

```bash
# Clone repository
git clone https://github.com/gottino/rmirror-cloud
cd rmirror-cloud

# Backend setup
cd backend
poetry install
cp .env.example .env
# Edit .env with your Google AI API key and database URL
poetry run alembic upgrade head
poetry run uvicorn app.main:app --reload

# Dashboard setup (separate terminal)
cd dashboard
npm install
cp .env.example .env.local
# Edit .env.local with backend URL and Clerk keys
npm run dev

# Agent setup (separate terminal)
cd agent
poetry install
poetry run python -m app.main --foreground --debug
```

Visit `http://localhost:3000` for the dashboard, `http://localhost:9090` for agent config.

See [Development Setup](#-development-setup) for detailed instructions.

---

## 📦 Architecture

```
┌─────────────────┐
│   Mac Agent     │  ← Python background service (v1.6.0)
│  (Menu Bar App) │     File watching + Flask web UI
└────────┬────────┘
         │ HTTPS (JWT auth)
         ↓
┌─────────────────────────────────────┐
│       Cloud Backend (Hetzner)       │
│                                     │
│  ┌──────────────┐  ┌─────────────┐ │
│  │  FastAPI     │  │ PostgreSQL  │ │
│  │  REST API    │  │  (SQLite in │ │
│  └──────┬───────┘  │   dev mode) │ │
│         │          └─────────────┘ │
│  ┌──────▼───────┐                  │
│  │ OCR Pipeline │  ┌─────────────┐ │
│  │ Gemini Vision│  │ Quota System│ │
│  └──────────────┘  └─────────────┘ │
│                                     │
│  ┌──────────────┐  ┌─────────────┐ │
│  │ Sync Workers │  │ S3 Storage  │ │
│  │  (Asyncio)   │  │ (Backblaze) │ │
│  └──────────────┘  └─────────────┘ │
└─────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────┐
│   Next.js Dashboard (Vercel)        │
│  ┌──────────────────────────────┐   │
│  │  Clerk Auth (Google OAuth)   │   │
│  └──────────────────────────────┘   │
│  ┌──────────────────────────────┐   │
│  │  Notebook Browser + Search   │   │
│  └──────────────────────────────┘   │
│  ┌──────────────────────────────┐   │
│  │  Integration Management      │   │
│  └──────────────────────────────┘   │
└─────────────────────────────────────┘
         │
         ↓
   External APIs
   (Notion OAuth, Obsidian, Readwise planned)
```

**Components:**

- **Agent** (`agent/`) - macOS background service with menu bar app and localhost web UI (port 9090)
- **Backend** (`backend/`) - FastAPI server with asyncio sync workers, quota enforcement, OCR pipeline
- **Dashboard** (`dashboard/`) - Next.js 14 web interface with Clerk authentication
- **Database** - PostgreSQL (production), SQLite (development)
- **Storage** - S3-compatible (Backblaze B2 for production)

---

## 🛠️ Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Agent | Python + Flask + rumps | Lightweight, native macOS menu bar integration |
| Backend | FastAPI + SQLAlchemy | Async Python, type-safe, auto-generated OpenAPI docs |
| Database | PostgreSQL / SQLite | Robust for production, simple for dev |
| OCR | Google Gemini 2.5 Flash | Best quality/cost ratio for handwriting OCR |
| Storage | S3-compatible (Backblaze B2) | Scalable, cost-effective object storage |
| Dashboard | Next.js 14 + Clerk | SSR, great DX, managed authentication |
| Auth | JWT (30-day tokens) | Stateless, secure, long-lived for agent |
| Deployment | Hetzner VPS + Vercel | Backend on VPS, frontend on edge network |

---

## 🎯 Current Status (March 2026)

### ✅ Production Ready

**Core Backend**
- [x] FastAPI REST API with JWT authentication
- [x] User management & authorization
- [x] Notebook & page storage with folder hierarchy
- [x] Database migrations (Alembic)
- [x] Production deployment on Hetzner VPS
- [x] CI/CD with GitHub Actions
- [x] S3-compatible storage (Backblaze B2)

**OCR & Processing**
- [x] Gemini 2.5 Flash Vision API
- [x] OCR processing pipeline
- [x] PDF generation from reMarkable files
- [x] Handwriting recognition with context awareness

**Quota System**
- [x] Beta tier: 200 pages/month OCR processing
- [x] Graceful degradation when quota exhausted
  - Uploads accepted, PDFs generated
  - OCR deferred with `PENDING_QUOTA` status
  - Retroactive processing when quota resets (newest pages first)
- [x] Email notifications (90% warning, 100% exhausted)
- [x] HTTP 402 status code with quota details in response
- [x] Dashboard quota display with usage bar
- [x] Agent quota display with color-coded status

**Integrations**
- [x] Notion OAuth integration
- [x] Notion database sync with markdown formatting
- [x] Background sync workers (asyncio-based, polls every 5s)
- [x] Database-driven deduplication using `page_uuid`
- [x] Two-phase initial sync (notebooks first, then pages)
- [x] Metadata-only sync (50-100x faster, ~100ms vs ~5s)
  - Updates Notion properties: `last_opened`, `page_count`, `path`
  - Separate from full content sync
- [x] Page limit control for initial sync (prevents quota exhaustion)
- [x] Obsidian vault sync via plugin

**macOS Agent**
- [x] Python background service with menu bar app
- [x] File watching & automatic sync to cloud
- [x] Flask web UI for configuration (localhost:9090)
- [x] Intelligent sync queue with batching
- [x] Exponential backoff retry logic
- [x] Long-lived token authentication (30-day JWT)
- [x] Quota display in menu bar and web UI
- [x] Production release v1.6.0 with `.app` bundle
- [x] Automation scripts for build and release
- [x] Auth bridge for agent authentication
- [x] Per-notebook deletion support

**Web Dashboard**
- [x] Next.js 14 web interface (deployed on Vercel)
- [x] Clerk authentication (Google OAuth)
- [x] Notebook browsing with folder hierarchy
- [x] PDF viewer for pages
- [x] Integration configuration (Notion OAuth)
- [x] Quota display with upgrade CTAs
- [x] Quota exceeded modal on HTTP 402 errors
- [x] Responsive design (mobile-friendly)

**Documentation**
- [x] Comprehensive API reference
- [x] Deployment guides
- [x] Development setup documentation
- [x] Domain-specific `.claudecontext` files
- [x] Legal compliance (Privacy Policy, Terms of Service, DPA)

**Tooling**
- [x] OCR benchmark tool for model evaluation
- [x] Analytics integration

### 🚧 Planned

**Phase 2: Monetization**
- [ ] Stripe integration for paid tiers
- [ ] Pro tier: Unlimited OCR processing
- [ ] Enterprise tier: Custom quota, priority support

**Integrations**
- [ ] Readwise integration
- [ ] Todo app integration (other than Notion)

**Agent**
- [ ] Windows and Linux support
- [ ] Signed & notarized macOS installer (.pkg)
- [ ] Auto-update mechanism

**Polish**
- [ ] Performance optimization (caching, database indexing)
- [ ] End-to-end encryption option
- [ ] Multi-language support

**Launch**
- [ ] Public beta
- [ ] Managed cloud service pricing
- [ ] Marketing website

---

## 🔧 Development Setup

### Prerequisites

- Python 3.11 or later
- Node.js 18 or later
- Poetry (Python dependency management)
- PostgreSQL (production) or SQLite (development)
- Google AI API key (for OCR)
- Clerk account (for dashboard authentication)

### Backend Setup

```bash
cd backend

# Install dependencies
poetry install

# Create environment file
cp .env.example .env

# Edit .env and set:
# - DATABASE_URL (use SQLite for dev: sqlite:///./rmirror.db)
# - GOOGLE_AI_API_KEY (get from aistudio.google.com)
# - SECRET_KEY (generate with: openssl rand -hex 32)

# Run database migrations
poetry run alembic upgrade head

# Start development server
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend runs at `http://localhost:8000`. API docs at `http://localhost:8000/docs`.

**Database Management:**

```bash
# Create new migration
poetry run alembic revision -m "description"

# Apply migrations
poetry run alembic upgrade head

# Rollback one migration
poetry run alembic downgrade -1

# View current revision
poetry run alembic current
```

### Dashboard Setup

```bash
cd dashboard

# Install dependencies
npm install

# Create environment file
cp .env.example .env.local

# Edit .env.local and set:
# - NEXT_PUBLIC_API_URL=http://localhost:8000
# - NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY (get from clerk.com)
# - CLERK_SECRET_KEY (get from clerk.com)

# Start development server
npm run dev
```

Dashboard runs at `http://localhost:3000`.

### Agent Setup

```bash
cd agent

# Install dependencies
poetry install

# Start in foreground mode with debug logging
poetry run python -m app.main --foreground --debug

# Build macOS .app bundle
./build_macos.sh
```

Agent web UI runs at `http://localhost:9090`.

**Configuration:**
- Config stored at `~/.rmirror/config.yaml`
- Token stored in system keychain (secure)
- Requires Full Disk Access permission on macOS

### Testing

```bash
# Backend tests
cd backend
poetry run pytest
poetry run pytest -v  # verbose
poetry run pytest tests/test_specific.py  # specific file

# Dashboard (no tests yet)
cd dashboard
npm run test
```

### Multi-Instance Development Workflow

This repository uses **domain-specific `.claudecontext` files** for focused development:

```bash
# Backend work - Start Claude Code session here
cd backend
# Reads backend/.claudecontext automatically

# Dashboard work - Separate session
cd dashboard
# Reads dashboard/.claudecontext automatically

# Agent work - Separate session
cd agent
# Reads agent/.claudecontext automatically
```

**Why separate sessions?**
- Focused context (only loads what you need)
- Faster responses (less context to process)
- Cleaner history (backend changes don't pollute dashboard session)

See `CLAUDE.md` for detailed guidance on working with this repository.

---

## 🏗️ Key Architectural Patterns

### Quota System

**Three-tier enforcement:**

1. **Backend validation** - Check quota before OCR processing
2. **Graceful degradation** - Accept uploads when exhausted, defer OCR
3. **HTTP 402** - Return quota details in error response

**Flow when quota exhausted:**

```
User uploads page → Backend accepts upload → Generate PDF → Store in S3
→ Check quota → Quota exhausted → Set status to PENDING_QUOTA
→ Return HTTP 402 → Dashboard shows "OCR Pending" badge
→ User sees PDF, no OCR text yet
→ Quota resets → Background worker processes PENDING_QUOTA pages (newest first)
```

**Tables:**

- `subscriptions`: User's subscription tier (free/pro/enterprise)
- `quota_usage`: Current usage and limit per user per quota type
- `pages`: `ocr_status` field: `pending`, `completed`, `failed`, `pending_quota`

### Background Sync Workers

**Asyncio-based polling** (every 5 seconds):

1. Query `sync_queue` table for pending items
2. Group by `user_id` for batch processing
3. Process each sync task (upload to Notion, Readwise, etc.)
4. Update `sync_records` table with external IDs
5. Mark queue item as `completed` or `failed`

**Critical patterns:**

- Must use `async`/`await` throughout
- Close SQLAlchemy sessions in `finally` blocks
- Handle archived blocks gracefully (catch "Can't edit block that is archived")
- Use `page_uuid` for deduplication (NOT `content_hash`)

### Database-Driven Deduplication

**Source of truth:** `sync_records` table

```sql
-- Unique constraint prevents duplicates
UNIQUE (page_uuid, target_name, user_id)
```

**Upsert pattern:**

1. Query `sync_records` by `page_uuid` + `target_name` + `user_id`
2. If exists → Update external block/page
3. If not exists → Create new block/page, insert record

**Why `page_uuid` not `content_hash`?**

- reMarkable provides stable UUIDs for pages
- Content changes shouldn't create duplicates
- Enables metadata-only updates without re-OCR

### Metadata-Only Sync

**50-100x faster than full content sync** (~100ms vs ~5s):

- Updates only Notion properties: `last_opened`, `page_count`, `path`, `type`
- No OCR, no PDF upload, no block creation
- Triggered by metadata changes (notebook renamed, page reordered, etc.)

**Queue item types:**

- `NOTEBOOK` → Full content sync (OCR + Notion blocks)
- `NOTEBOOK_METADATA` → Metadata-only sync (properties only)

---

## 📚 Documentation

- **[📖 Complete Documentation](docs/)** - Comprehensive project documentation
- **[Architecture Overview](docs/architecture.md)** - System design and components
- **[API Reference](docs/api/backend-api.md)** - Complete REST API documentation
- **[Development Setup](docs/development/setup.md)** - Get started with development
- **[Deployment Guide](docs/deployment/hetzner.md)** - Production deployment
- **[Contributing Guidelines](CONTRIBUTING.md)** - How to contribute

---

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**Areas needing help:**

- 🎨 UI/UX improvements for dashboard
- 🧪 Testing on Windows/Linux (agent currently macOS-only)
- 📝 Documentation improvements
- 🔌 New connector integrations (Readwise, Obsidian)
- 🌍 Internationalization
- 🐛 Bug reports and fixes

**Before contributing:**

1. Read `CLAUDE.md` for project context
2. Check existing issues and PRs
3. Open an issue for major changes
4. Follow code style (Black for Python, Prettier for TypeScript)
5. Write tests for new features

---

## 🔗 Related Projects

- **[remarkable-integration](https://github.com/gottino/remarkable-integration)** - Local CLI tool for advanced users
  - Perfect if you want full local control
  - Python-based, SQLite database
  - No cloud service required

**Which should you use?**

- **rMirror Cloud**: Easier setup, access from anywhere, web dashboard, automatic sync
- **remarkable-integration CLI**: Local control, no cloud dependency, scriptable, advanced users

Both are open source. Both work great. Pick what fits your workflow!

---

## 💬 Community

- **Discord**: [Join our server](https://discord.gg/rmirror)
- **Discussions**: [GitHub Discussions](https://github.com/gottino/rmirror-cloud/discussions)
- **Issues**: [Report bugs](https://github.com/gottino/rmirror-cloud/issues)
- **Twitter**: [@rmirror_cloud](https://twitter.com/rmirror_cloud)

---

## 📄 License

**AGPL-3.0** - See [LICENSE](LICENSE)

This means:

- ✅ Free to use, modify, and self-host
- ✅ Commercial use allowed
- ✅ Can build your own features and integrations
- ⚠️ Must open source any modifications if you run a public service
- ⚠️ Cannot create closed-source competing cloud service

**Why AGPL?** Protects the open source nature while allowing self-hosting. Companies wanting private modifications can contact us about commercial licensing.

---

## 🙏 Acknowledgments

Built with ❤️ using:

- [Google Gemini](https://deepmind.google/technologies/gemini/) for AI-powered OCR
- [FastAPI](https://fastapi.tiangolo.com) for the backend
- [Next.js](https://nextjs.org) for the web dashboard
- [Clerk](https://clerk.com) for authentication
- [Python](https://python.org) for the macOS agent

Special thanks to the reMarkable community for inspiration and feedback.

---

## 📞 Support

**Self-hosting questions?** Check [docs/](docs/) or [Discussions](https://github.com/gottino/rmirror-cloud/discussions)

**Found a bug?** [Open an issue](https://github.com/gottino/rmirror-cloud/issues)

**Feature request?** [Start a discussion](https://github.com/gottino/rmirror-cloud/discussions/new?category=ideas)

**Need enterprise support?** Email enterprise@rmirror.io

---

**Made with reMarkable 📝**
