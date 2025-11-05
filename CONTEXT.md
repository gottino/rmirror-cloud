# Development Context & Session Notes

**Last Updated:** January 5, 2025
**Status:** Initial setup complete, ready for Phase 1 implementation

---

## Project Overview

**rMirror Cloud** - Open source cloud service for reMarkable tablet integration. Transform the existing local CLI tool (remarkable-integration) into a scalable cloud platform with agent + web dashboard.

**Repository:** rmirror-cloud (new project)
**Related:** remarkable-integration (existing local CLI tool, separate repo)

---

## Current State

### ✅ Completed (Initial Setup)

1. **Repository Structure Created**
   - Monorepo: agent/, backend/, dashboard/, docs/, infrastructure/
   - Docker Compose for local development
   - AGPL-3.0 license
   - Comprehensive documentation

2. **Core Documents**
   - README.md: Project overview, features, quick start
   - CONTRIBUTING.md: Contribution guidelines
   - docs/architecture.md: System architecture for 100-1000 users
   - concepts/implementation-strategy.md: Detailed phase-by-phase plan
   - concepts/remarkable-cloud-complete.md: Original strategic concept

3. **Development Environment**
   - docker-compose.yml: PostgreSQL, Redis, MinIO (S3-compatible)
   - .env.example: Environment variable template
   - .gitignore: Proper exclusions (includes concepts/)

### 📋 Next Steps (Phase 1: Foundation)

**Immediate priorities for Week 1-2:**

1. **Infrastructure Provisioning**
   - [ ] Create DigitalOcean account
   - [ ] Reserve domains (rmirror.io)
   - [ ] Set up Cloudflare DNS
   - [ ] Provision managed PostgreSQL, Redis, Spaces

2. **Backend Development** (Week 2-4)
   - [ ] Set up FastAPI project structure
   - [ ] Implement database models (SQLAlchemy)
   - [ ] Create authentication system
   - [ ] Build file upload endpoint
   - [ ] Set up Alembic migrations

3. **Local Development**
   - [ ] Test Docker Compose stack
   - [ ] Verify database connectivity
   - [ ] Test S3 (MinIO) uploads
   - [ ] Run initial migrations

---

## Key Architectural Decisions

### Technology Stack

| Component | Choice | Why |
|-----------|--------|-----|
| Agent | Tauri 2.0 | 10MB installer, cross-platform, native performance |
| Backend | FastAPI + Uvicorn | Async Python, reuses existing code |
| Database | PostgreSQL 15 | JSONB support, row-level security |
| Queue | Redis + RQ | Simple, Python-native, sufficient for <1K users |
| Storage | DigitalOcean Spaces | S3-compatible, $5/250GB |
| Dashboard | Next.js 14 + Vercel | Free hosting, auto-scaling |
| Auth | Supabase Auth | Managed, OAuth support |

### Scaling Strategy

- **1-100 users:** Single app instance (~$50/mo)
- **100-500 users:** Load balancer, 2 instances (~$250/mo)
- **500-1000 users:** 3 instances, read replica (~$500/mo)
- **1000+ users:** Kubernetes, autoscaling (~$1000+/mo)

### Multi-Tenancy Approach

- **Row-level security** in PostgreSQL
- All tables have `user_id` column
- RLS policies enforce data isolation
- One database, multiple tenants

---

## Code Reuse Strategy

### From remarkable-integration (Local CLI)

**Core processing logic to port:**

```
remarkable-integration/src/processors/
├── enhanced_highlight_extractor.py   → backend/app/core/highlight_extractor.py
├── epub_text_matcher.py              → backend/app/core/epub_matcher.py
├── pdf_text_matcher.py               → backend/app/core/pdf_matcher.py
└── rm scene parsing logic            → backend/app/core/rm_converter.py
```

**Approach:** Copy and adapt (not package dependency)
- Removes file system dependencies
- Adapts to work with bytes/streams
- Integrates with cloud storage (S3)

**Key files to reference:**
- `src/processors/enhanced_highlight_extractor.py` (main extraction logic)
- `src/processors/epub_text_matcher.py` (EPUB text matching)
- `src/integrations/readwise_sync.py` (Readwise integration pattern)
- `src/core/file_watcher.py` (file watching logic for agent)

---

## Database Schema Summary

### Core Tables

**users** - Authentication and subscription
- `id`, `email`, `subscription_tier`, `api_key_hash`

**notebooks** - reMarkable notebooks/documents
- `user_id`, `notebook_uuid`, `visible_name`, `document_type`

**pages** - Individual pages with OCR tracking
- `notebook_id`, `page_number`, `file_hash`, `ocr_status`, `ocr_text`

**highlights** - Extracted highlights from PDFs/EPUBs
- `user_id`, `notebook_id`, `original_text`, `corrected_text`

**sync_records** - Tracks external service syncs
- `item_type`, `item_id`, `target_service`, `content_hash`

**processing_jobs** - Async job queue
- `job_type`, `status`, `input_data`, `result_data`

**connectors** - User's connected services
- `service_name`, `credentials_encrypted`, `settings`

---

## Important Context from Previous Project

### Quality Filters (Implemented Oct 2025)

Strict quality filtering for highlight extraction:
- Minimum 60% alphabetic characters
- At least 3 words
- Maximum 20% symbols
- Max 3 consecutive non-alphanumeric characters

**Rationale:** Prevents gibberish extraction (was 49% of highlights before filtering)

### EPUB Text Matching (Implemented Oct 2025)

Two-stage pipeline for cleanest text:
1. Match .rm annotation → PDF text
2. Match PDF text → EPUB source (±10% window)
3. Validate with fuzzy matching (85% score, 70% similarity)
4. Fallback to PDF text if no match

**Performance:** ~15-20 seconds for 19 highlights, eliminates ligatures and encoding issues

### Readwise Integration Lessons

- Deduplication by `title + author + source`
- Must use real authors (not "reMarkable")
- Cover images need public URLs (cloud storage)
- Manual duplicate cleanup required (API doesn't support deletion)

---

## Development Environment Setup

### Prerequisites

- Docker & Docker Compose
- Python 3.11+ with Poetry
- Node.js 18+
- Rust 1.70+ (for agent)

### Quick Start

```bash
# Clone and setup
git clone https://github.com/gottino/rmirror-cloud
cd rmirror-cloud
cp .env.example .env
# Edit .env with Claude API key

# Start infrastructure
docker-compose up -d postgres redis minio

# Backend (when ready)
cd backend
poetry install
poetry run alembic upgrade head
poetry run uvicorn app.main:app --reload

# Dashboard (when ready)
cd dashboard
npm install
npm run dev

# Agent (when ready)
cd agent
npm install
npm run tauri dev
```

---

## Key Files to Reference

### From This Repository (rmirror-cloud)

- **concepts/implementation-strategy.md** - Detailed phase-by-phase plan
- **concepts/remarkable-cloud-complete.md** - Strategic vision and business model
- **docs/architecture.md** - Technical architecture
- **README.md** - User-facing documentation
- **docker-compose.yml** - Local dev environment

### From Related Repository (remarkable-integration)

- **src/processors/enhanced_highlight_extractor.py** - Core extraction logic
- **src/processors/epub_text_matcher.py** - Text matching implementation
- **src/core/file_watcher.py** - File watching patterns
- **src/integrations/readwise_sync.py** - External service integration pattern
- **CHANGELOG.md** - Feature history and lessons learned

---

## Questions for Next Session

### Infrastructure
- Which cloud provider? (Recommended: DigitalOcean for simplicity)
- Which region? (Based on primary user location)
- Domain procurement strategy?

### Development
- Start with backend or agent?
- Local dev first or cloud deployment first?
- Testing strategy (manual vs automated)?

### Business
- Self-hosting focus or managed service focus initially?
- Open source launch timeline?
- Beta tester recruitment strategy?

---

## Cost Estimates

### Year 1 (Conservative)

**Infrastructure:** $2,000-3,000
- DigitalOcean: $50-300/month (scales with users)
- Monitoring: $29-49/month
- Domain: $15/year

**Revenue Potential:**
- Month 6: 100 users, 10 paying = $100/mo MRR
- Month 12: 500 users, 50 paying = $500/mo MRR

**Break-even:** Month 10-12

---

## Notes for Claude Code

When starting the next session in rmirror-cloud:

1. **Read these files first:**
   - This file (CONTEXT.md)
   - concepts/implementation-strategy.md
   - docs/architecture.md

2. **Reference patterns from remarkable-integration:**
   - File watching: `src/core/file_watcher.py`
   - Highlight extraction: `src/processors/enhanced_highlight_extractor.py`
   - Text matching: `src/processors/epub_text_matcher.py`

3. **Start with Phase 1, Week 1-2:**
   - Infrastructure provisioning
   - FastAPI project setup
   - Database models and migrations

4. **Use TodoWrite tool** for task tracking throughout development

---

**Remember:** This is a new product, not a refactor. Clean slate to build cloud-native architecture while reusing proven processing logic.
