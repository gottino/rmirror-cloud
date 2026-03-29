# Changelog

All notable changes to the rMirror Cloud project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### OCR Model Switch to Gemini 2.5 Flash (2026-03-29)
- **Benchmarked 5 OCR models** across 3 providers (Anthropic, OpenAI, Google) on real reMarkable handwriting samples
- **Gemini 2.5 Flash selected** as new default: composite quality score 0.699, cost $0.003/page vs $0.007 for Claude Haiku
- **Scoring dimensions**: CER (character error rate), line accuracy, structure detection, heading recognition
- **Provider cost comparison** documented in benchmark results

#### OCR Benchmark Tool (2026-03-28)
- **Standalone `benchmark/` tool** for evaluating OCR quality across providers
- **`benchmark/run.py`**: multi-provider execution loop with dry-run support and meta.yaml output
- **`benchmark/score.py`**: CER, line accuracy, and structure metrics scoring
- **Synthetic test fixture** for benchmark smoke testing without real API calls
- **Cost estimates** included in benchmark output for provider comparison

#### Agent Auth Bridge (2026-03-28)
- **Self-hosted Clerk auth page** (`/agent-auth`) for agent login flow, replacing redirect to dashboard
- **Public route** exempt from Clerk middleware protection
- **Clerk JS SDK pinned to v4** for stability
- **Callback URL preserved** on sign-out to resume the auth flow after re-login
- **Environment switching** between staging and production Clerk instances
- **rM logo** replaces notebook emoji on the auth bridge page

#### Per-Notebook Deletion (2026-03-22)
- **Cascade delete** removes pages, notebook-page mappings, sync queue entries, and sync records
- **S3/B2 object cleanup** for all PDFs associated with deleted notebooks
- **Agent awareness** of server-side deletions
- **Complete cleanup** prevents orphaned sync records from causing duplicate detection issues

#### Obsidian Integration (2026-03-15)
- **API key authentication** for Obsidian plugin access (SHA-256 hashed keys stored in database)
- **Content hash-based sync**: `obsidian_content_hash` tracks last-synced content to skip unchanged pages
- **Obsidian API endpoints** registered under `/v1/obsidian`
- **Dashboard integration card** with API key generation and management UI
- **Excluded from push-based sync queue** (pull-only model via plugin)
- **Backfill migration** for `obsidian_content_hash` on pre-existing notebooks

#### Admin Dashboard (2026-02-28)
- **Waitlist management** view for monitoring and acting on beta signups
- **User onboarding milestones** display: agent install, first upload, Notion connected
- **Admin-only routes** protected by user ID allowlist

#### Beta User Quota System (2026-02-22)
- **200 pages/month quota** for beta users (vs 30 pages/month free tier)
- **`is_beta_user` flag** on user model for manual and automated enrollment
- **Auto-enrollment via Clerk webhook** on new user registration during beta period

#### Umami Analytics (2026-02-20)
- **Self-hosted Umami** on `analytics.rmirror.io` for cookie-less, privacy-respecting tracking
- **End-to-end event tracking** across dashboard and landing page
- **Backend env vars** added to production deploy workflow

#### Legal Compliance (2026-02-20)
- **Version-based terms and privacy acceptance** flow: users must accept current version on login
- **Public legal pages** at `/legal/privacy` and `/legal/terms` (no auth required)
- **Acceptance recorded** in database with version and timestamp

#### Onboarding and Drip Campaign (2026-02-15)
- **Onboarding checklist** in dashboard sidebar with milestone tracking (agent install, first sync, Notion connected)
- **Automated email drip campaign** with sequenced onboarding messages via Resend
- **Two-phase onboarding flow** consolidating setup steps
- **Support email** and Notion feedback form links added to sidebar

#### Open Signups (2026-03-01)
- **Removed invite gate** - signups open to all without waitlist approval
- **Setup wizard** with Gatekeeper bypass instructions for macOS notarization
- **`GET /agents/latest-version`** public endpoint for dashboard download link (no hardcoded URLs)
- **Pre-download funnel** with setup wizard before DMG download

#### Agent v1.6.0 (2026-03-29)
- **Version bump** to 1.6.0 with backend `agent_latest_version` config updated

#### Agent v1.5.6 (2026-03-22)
- **Auth popup blocker fix** - resolved issue preventing Clerk sign-in window from opening
- **Config save crash fix** and restart hang resolved

#### Agent v1.5.5 (2026-03-16)
- **W^X entitlement** added for Intel build to satisfy macOS security requirements
- **Inside-out signing** for Intel DMG (sign binaries before bundling)
- **`disable-library-validation`** entitlement for Intel builds

#### Agent v1.5.4 (2026-03-10)
- **Graceful handling of missing reMarkable folder** - logs warning instead of crashing on startup

#### Agent v1.5.3 (2026-03-05)
- **Setup wizard polish** with Gatekeeper note and sync screenshot

#### Agent v1.5.2 (2026-02-28)
- **Intel DMG build** via GitHub Actions `build-agent-intel.yml` workflow (`macos-15-intel` runner)
- **B2 auth fix** in Intel build workflow

#### Agent v1.5.1 (2026-02-22)
- **Template filtering** - skip reMarkable built-in templates in all metadata parsers

#### Agent v1.5.0 (2026-02-10)
- **Auto-update feature** with user-triggered update checking
- **Build script fix** for macOS app bundle generation

#### CI/CD Pipeline (2026-02-08)
- **Comprehensive CI workflow** for backend (pytest), dashboard (lint + build), and agent
- **Staging environment** with separate deployment workflow
- **Apple Silicon build workflow** (`build-agent.yml`) on `macos-15` runner
- **CLERK_JWKS_URL and DEBUG** environment variables added to deployment workflows

#### Search and Discovery (2026-02-05)
- **Fuzzy full-text search** across notebook names and OCR content
- **Folder, date, and in-notebook filters** for search refinement
- **Content matches weighted higher** than name matches in result ranking
- **Notebook-level pagination** instead of raw match pagination

#### Security Hardening (2026-02-06)
- **5 critical security vulnerabilities patched**: SSL verification, JWT bypass, OAuth CSRF, encryption bypass, SQL injection
- **Phase 4 medium priority fixes**: HMAC-signed OAuth state, parameterized PostgreSQL SET commands
- **CLERK_JWKS_URL** required in production (raises RuntimeError if missing)
- **Dev mode bypass** hardened with localhost check

#### Structured Logging and Observability (2026-02-04)
- **Structured JSON logging** for all backend requests
- **Request tracing** with correlation IDs
- **Health check endpoints** for uptime monitoring

#### Notebook Export (2026-02-01)
- **Markdown export** of OCR text per notebook
- **PDF export** with placeholder PDFs for pages without stored PDFs
- **Settings page** with data export and account deletion (Danger Zone)
- **Account export** query aligned with notebook detail endpoint

#### Documentation Update (2026-01-21)
- **Comprehensive documentation refresh** for January 2026 state
- **Updated README.md** with current architecture and features
- **Updated docs/architecture.md** with new data flows and diagrams
- **Updated docs/api/backend-api.md** with new endpoints (quota, metadata sync, agent token)
- **Updated docs/README.md** with production-ready component statuses

#### Agent v1.4.1 Release (2026-01-12)
- **Deleted pages filtering** - skip pages marked as deleted in .content files
- **UUID truncation bug fix** - use `removesuffix(".rm")` instead of `rstrip(".rm")`
- **Automation scripts** for release management

#### Two-Phase Initial Sync (2026-01-08)
- **Sequential notebook creation** - create Notion pages first before queuing page blocks
- **Row-level queue locking** with `FOR UPDATE SKIP LOCKED` to prevent duplicates
- **Batch status update** - mark all items as 'processing' before processing loop
- **Database-driven notebook deduplication** - track notebook page ID in SyncRecord

#### Metadata-Only Sync (2026-01-06)
- **NOTEBOOK_METADATA sync item type** for fast metadata updates
- **50-100x faster sync** (~100ms vs ~5s) for metadata-only changes
- **Notion property updates** without content block modifications
- **Triggered on .metadata file changes** from reMarkable

#### Quota System Phase 1 (2026-01-05)
- **Free tier limits** - 30 pages/month OCR quota
- **Graceful degradation** - accept uploads when quota exhausted, defer OCR
- **PENDING_QUOTA page status** - pages awaiting quota for OCR processing
- **HTTP 402 error responses** with quota details
- **Retroactive processing** - newest pages first when quota resets
- **Email notifications** at 90% and 100% quota usage
- **Dashboard quota display** with color-coded status indicators
- **Agent quota display** in menu bar and web UI

#### Long-Lived Agent Tokens (2026-01-04)
- **30-day JWT tokens** for agent authentication
- **Token exchange endpoint** `/auth/agent-token` - exchange Clerk token for agent token
- **Secure callback validation** - only localhost callbacks allowed
- **System keychain storage** for secure token persistence

#### User-Aware Rate Limiting (2026-01-03)
- **Per-user rate limits** for authenticated requests (300/min)
- **Per-IP rate limits** for unauthenticated requests (30/min)
- **Auth endpoint limits** (10/min)
- **Metadata sync limits** (100/min - higher for lightweight operations)

#### OCR Deduplication System (2025-12-26)
- **SHA-256 file hashing** for .rm files to track content changes
- **Smart OCR deduplication** - skips OCR processing for unchanged files
- **Hash backfilling utilities** for existing pages without hashes
  - `backfill_page_hashes.py` - Backfill hashes from reMarkable source directory
  - `backfill_by_metadata.py` - Advanced metadata-based backfilling
  - `backfill_specific_notebooks.py` - Targeted notebook hash backfilling
- **Hash coverage reporting** - `hash_coverage_report.py` to analyze coverage by notebook
- **Missing pages detection** - `show_missing_pages_summary.py` utility
- **Database comparison tool** - `check_content_vs_db.py` to verify sync integrity

#### Initial Sync Feature (2025-12-25)
- **Initial Sync API endpoint** for catch-up scenarios
- **Web UI Initial Sync button** in agent interface at localhost:5555
- **Bulk notebook upload** functionality
- **Smart selective sync** respecting notebook selection configuration
- Support for first-time setup and offline catch-up scenarios

#### Page Ordering Improvements (2025-12-25)
- **Use .content files as source of truth** for notebook page ordering
- **Orphan page migration** - move pages to correct notebooks based on .content files
- **cPages format support** for newer reMarkable firmware
- **Automatic duplicate page removal** during sync
- **Removed page_number column** from pages table (now in mapping table)
- Pages ordered correctly in API responses

#### PostgreSQL Migration (2025-12-22)
- **Fully automated migration script** - `migrate_to_postgres.sh`
- **Interactive setup** with colored output and confirmations
- **Automatic data migration** from SQLite to PostgreSQL
- **Boolean type conversion** handling for SQLite to PostgreSQL migration
- **All tables migration** including agent_registrations
- **Quick start guide** in `scripts/POSTGRES_MIGRATION.md`

#### Dashboard Design System (2025-12-20 to 2025-12-21)
- **Unified design system** with warm, sophisticated color palette
- **Mobile-responsive sidebar** with collapsible navigation
- **OCR content previews** in page listings
- **Folder navigation with breadcrumbs** for notebook hierarchy
- **Improved notebook detail view** aligned with design system
- **Better logo spacing and alignment** in header

#### Selective Notebook Sync (2025-12-19)
- **Notebook selection UI** with collapsible folders
- **Date-based notebook grouping** for easier selection
- **Free tier sync limits** with selective sync configuration
- **Standalone app mode** with auto-launch browser
- **Default browser detection** on macOS

#### Authentication & Security (2025-12-16 to 2025-12-21)
- **Local development mode** with secure authentication bypass
  - DEBUG-gated dev-mode-bypass token (backend only when DEBUG=true)
  - NEXT_PUBLIC_DEV_MODE flag for dashboard development
  - Production security remains unchanged with full Clerk authentication
- **OAuth authentication** and onboarding tracking
- **Clerk authentication** for all sync and processing endpoints
- **Immediate file watcher start** after authentication
- **Agent registration logging** for debugging

#### Deployment & Infrastructure (2025-12-07 to 2025-12-08)
- **Backblaze B2 storage configuration** for production file storage
- **macOS installer build system** with automated deployment
- **Beta page** with installer download functionality
- **Automated nginx config deployment** with landing pages
- **Production nginx configuration** with beta.html support
- **Deployment workflow improvements** with git conflict resolution
- **Test user cleanup utility** for development

#### Email Notifications (2025-12-07)
- **Resend email integration** for user communications
- **Welcome email** sent on user registration
- **Email monitoring** and notification system
- **Secure API key management** via GitHub Secrets
- **Webhook signature verification** using official Svix library

#### UI/UX Improvements (2025-12-17)
- **Improved notebook page UI** with better layout
- **Next.js security update** to version 15.5.9
- **React state management fixes** for better performance
- **Home icon conflict resolution** with lucide-react

### Changed

#### Dependencies (2026-03-29)
- **FastAPI upgraded** from 0.109 to 0.135 for httpx 0.28 compatibility
- **httpx upgraded** from 0.26 to 0.28, required by google-genai SDK
- **google-genai** moved from dev to production dependencies
- **OCR provider changed** from Anthropic Claude Haiku to Google Gemini 2.5 Flash

#### Agent Web UI Port (2026-03-05)
- **Port changed from 5555 to 9090** for the agent local web interface

#### Notion Integration (2026-02-10)
- **Legacy `api_token` support deprecated** in favor of OAuth `access_token`
- **Improved initial sync** with full metadata support
- **`_get_http_client` helper** and `use_status_property` support added
- **Status property detection** for Notion todos sync

#### Dashboard Design (2026-02-05)
- **Moleskine design system applied** to Clerk authentication pages
- **Input border contrast improved** for accessibility
- **Auth flows kept within app domain** (no redirects to external Clerk pages)
- **Hero animation and responsive window chrome** improved on landing page
- **macOS Tahoe window chrome** added to landing page screenshots

### Fixed

#### Agent Signing (2026-03-16 to 2026-03-28)
- **W^X entitlement** added to resolve macOS security policy violations on Intel
- **Inside-out signing** for Intel DMG: sign all Mach-O binaries before app bundle signing
- **`disable-library-validation`** entitlement for Intel builds to allow dynamic library loading
- **All Mach-O binaries signed** in notarization workflow to pass Apple notarization

#### Auth Bridge (2026-03-28)
- **Clerk JS SDK pinned to v4** to prevent breaking changes from newer SDK versions
- **Callback URL preserved** when signing out on the agent auth bridge
- **CORS defaults** updated to include agent localhost origins
- **`CLERK_PUBLISHABLE_KEY` env var name** corrected to match Pydantic field definition

#### Obsidian Integration (2026-03-15)
- **`obsidian_content_hash` backfilled** for pre-existing notebooks via migration
- **Import sorting** fixed in backfill migration to pass ruff lint

#### Agent (2026-02-22 to 2026-03-22)
- **Auth popup blocker** resolved for agent Clerk sign-in window
- **Config save crash** and restart hang fixed in agent web UI
- **Keychain namespace** changes reflected in agent config tests
- **HS256 agent tokens** handled correctly in Clerk auth middleware
- **Agent auth API URL** reverted to `/v1` to match Nginx routing
- **f-string without placeholders** removed to pass ruff lint

#### Backend (2026-02-04 to 2026-03-01)
- **Ruff import sorting** fixes across drip service, migration files, and search service
- **PostgreSQL boolean default** uses `'false'` instead of `'0'`
- **Waitlist API** uses sync Session to avoid async session errors
- **Dev mode bypass** hardened with localhost-only check
- **Admin page auth** fixed for production use
- **SSL verification** respects `dev_mode` flag in update checker
- **Clerk auth enforced** on users API and onboarding endpoints
- **Quota tests** updated to mock `useQuota` context hook instead of `getQuotaStatus`

#### Mac Agent (2025-11-19)
- Python-based background service for automatic reMarkable sync
- Real-time file watching with watchdog library
- Intelligent sync queue with batching and deduplication
- Cloud sync client with JWT authentication
- Exponential backoff retry logic for failed uploads
- Flask web UI for configuration and monitoring (localhost:5555)
- CLI interface with foreground/background modes
- Support for .rm, .metadata, and .content files
- YAML-based configuration with Pydantic validation
- Automatic detection of reMarkable Desktop app folder on macOS
- Menu bar integration with rumps (2025-11-21)
  - System tray icon in macOS menu bar
  - Quick access to web UI and settings
  - Status display (Starting, Connected, Watching)
  - Graceful quit functionality

#### Todo Management (2025-11-17)
- Intelligent todo extraction from checkbox patterns in handwritten notes
- Support for multiple checkbox formats (Markdown `- [ ]`, Unicode `☐`, etc.)
- Fuzzy matching deduplication for OCR variations
- Todo CRUD API endpoints (list, get, update, delete)
- Todo statistics and filtering by notebook/completion status
- Background todo extraction with force reprocess option
- Page UUID tracking for cross-referencing with reMarkable files

#### Notion Integration (2025-11-17)
- Notion OAuth integration framework
- Markdown to Notion block converter
- Notebook sync to Notion with formatting preservation
- Support for headings, paragraphs, lists, and checkboxes
- Background sync processing
- Sync status tracking and statistics

#### Deployment & Infrastructure
- Production deployment on Hetzner Cloud (2025-11-09)
- GitHub Actions CI/CD pipeline for automated deployments
- Deploy user permissions and systemd service configuration
- Database migration scripts and backup system
- Deployment automation scripts

#### OCR Processing
- Claude Vision API integration for handwriting recognition
- Complete .rm file to text OCR pipeline
- .rm to PDF conversion
- Database integration for OCR results storage
- Batch processing support

#### Core Backend
- FastAPI REST API with comprehensive endpoints
- JWT-based authentication and authorization
- User management system
- Notebook and page storage
- File upload and S3-compatible storage (Backblaze B2)
- Database migrations with Alembic
- Folder hierarchy support for notebooks
- PDF generation from notebooks

### Changed

#### Documentation (2025-11-17)
- Reorganized documentation into centralized `docs/` structure
- Created comprehensive documentation index with quick start guide
- Moved API reference to `docs/api/backend-api.md`
- Moved deployment guides to `docs/deployment/`
- Moved development guides to `docs/development/`
- Updated roadmap from time-based to status-based (Completed/In Progress/Planned)
- Updated backend README with links to centralized docs

### Fixed

#### Database & Schema (2025-12-25)
- **Removed page_number column references** after migration to mapping table
- **Fixed page_number retrieval** from notebook_pages mapping table
- **Handle cPages format** correctly for newer reMarkable firmware
- **Remove duplicate pages** automatically during sync
- **Ensure correct page ordering** in API responses

#### PostgreSQL Migration (2025-12-22 to 2025-12-23)
- **Include all tables** in migration script (agent_registrations, etc.)
- **Convert SQLite integers to PostgreSQL booleans** correctly
- **Use full Poetry path** in migration script for reliability
- Made database migration idempotent to handle partial failures

#### Authentication & Security (2025-12-21)
- **Removed hardcoded authentication bypass** from production
- **Fixed development mode** to only work when DEBUG=true
- **Clerk authentication** properly enforced on all endpoints

#### Dashboard & UI (2025-12-17 to 2025-12-21)
- **Resolve Home naming conflict** with lucide-react icons
- **Fix useState placement** outside map function for React best practices
- **Update Next.js** to 15.5.9 to patch security vulnerabilities
- **Improve logo icon spacing** and alignment in header

#### Deployment & Infrastructure (2025-12-08)
- **Update last_synced_at** timestamp when syncing existing notebooks
- **Resolve deployment workflow** git conflicts and shell escaping
- **Correct Clerk redirect URLs** to /beta.html
- **Fix env variable injection** in deployment scripts
- **Use official Svix library** for webhook signature verification

#### macOS Agent (2025-12-19)
- **Use default browser** on macOS for opening web UI
- **Fix config validation** for YAML settings
- Removed redundant OCR trigger call causing 404 errors (OCR is automatic in /v1/processing/rm-file)
- Fixed async function handling in Flask web UI routes

#### Older Fixes (2025-11-10 to 2025-11-15)
- Added server_default for boolean columns in migration
- Fixed sudoers wildcards for systemctl flags
- Added both `/usr/bin/systemctl` and `/bin/systemctl` paths to sudoers
- Updated git pull to occur before deployment
- Auto-detect Poetry installation path in deploy script
- Updated Poetry install command for modern Poetry versions

---

## [0.1.0] - Initial Development Phase

### Added

#### Foundation
- Initial repository setup and project structure
- Database models (User, Notebook, Page, Highlight)
- SQLAlchemy ORM integration
- PostgreSQL/SQLite database support
- Alembic migration system

#### API Endpoints
- Authentication (login, register)
- User management
- Notebook CRUD operations
- File upload and storage
- Processing endpoints

#### File Processing
- reMarkable .rm file parsing
- SVG to PDF conversion
- Metadata extraction
- Folder structure support

#### Development Tools
- Migration script from remarkable-integration database
- Test scripts for OCR and integrations
- Development environment setup

---

## Project Milestones

### Completed Milestones

**Backend Foundation** (November 2025)
- ✅ Complete REST API with authentication
- ✅ OCR processing pipeline
- ✅ Database migrations and models
- ✅ Production deployment infrastructure

**Todo Extraction Feature** (November 2025)
- ✅ Pattern detection and extraction
- ✅ Intelligent deduplication
- ✅ Complete CRUD API
- ✅ Statistics and filtering

**Notion Integration** (November 2025)
- ✅ OAuth authentication
- ✅ Markdown formatting conversion
- ✅ Sync infrastructure
- ✅ Background processing

**Documentation** (November 2025)
- ✅ Complete API reference
- ✅ Deployment guides
- ✅ Development setup guides
- ✅ Centralized documentation structure

**Mac Agent v1.6.0** (March 2026)
- ✅ Python background service with menu bar integration
- ✅ Real-time file watching with watchdog
- ✅ Intelligent sync queue with batching
- ✅ Initial sync for catch-up scenarios
- ✅ Selective notebook sync configuration
- ✅ Quota display with color-coded status
- ✅ 30-day token authentication
- ✅ Auto-update with user-triggered version checking
- ✅ Intel and Apple Silicon DMG builds via GitHub Actions
- ✅ Self-hosted auth bridge for Clerk sign-in
- ✅ Graceful missing-folder handling

**Web Dashboard** (January 2026)
- ✅ Notebook browsing interface with folder navigation
- ✅ Page viewing with OCR text and PDF preview
- ✅ Quota management with upgrade CTAs
- ✅ Integration configuration (Notion OAuth)
- ✅ Clerk authentication (Google OAuth)
- ✅ Mobile-responsive design

**Quota System Phase 1** (January 2026)
- ✅ 30 pages/month free tier
- ✅ Graceful degradation
- ✅ Email notifications
- ✅ Dashboard and agent display

**Obsidian Integration** (March 2026)
- ✅ API key authentication for Obsidian plugin
- ✅ Content hash-based pull sync
- ✅ Dashboard integration card with key management
- ✅ Excluded from push-based sync queue

**OCR Benchmark and Gemini Migration** (March 2026)
- ✅ Standalone benchmark tool with multi-provider support
- ✅ CER, line accuracy, and structure scoring metrics
- ✅ Benchmarked 5 models across 3 providers
- ✅ Migrated OCR to Google Gemini 2.5 Flash ($0.003/page)

### Upcoming Milestones

**Stripe Integration** (Phase 2)
- Pro tier (500 pages/month)
- Enterprise tier (unlimited)
- Payment processing and billing

**Readwise Integration** (Planned)
- Highlight sync to Readwise
- Two-way sync support

---

## Version History

- **Unreleased** - Production-ready system with Gemini OCR, Obsidian integration, open signups, and full dashboard
- **Agent v1.6.0** - Self-hosted auth bridge, Intel + Apple Silicon builds, auto-update, graceful error handling
- **Agent v1.5.6** - Auth popup fix, config save crash fix
- **Agent v1.5.5** - Intel signing entitlements (W^X, disable-library-validation)
- **Agent v1.5.4** - Graceful missing reMarkable folder handling
- **Agent v1.5.3** - Setup wizard polish with Gatekeeper instructions
- **Agent v1.5.2** - Intel DMG build via GitHub Actions
- **Agent v1.5.1** - Template filtering in metadata parsers
- **Agent v1.5.0** - Auto-update feature
- **Agent v1.4.1** - Deleted pages filtering and UUID truncation bug fix
- **0.1.0** - Initial development phase with core backend and OCR processing

---

## Notes

This changelog documents the major features and changes to the rMirror Cloud project. For detailed commit history, see the [Git log](https://github.com/gottino/rmirror-cloud/commits/main).

For upcoming features and planned work, see the [Roadmap](README.md#-roadmap) in the main README.
