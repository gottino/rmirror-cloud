# Changelog

All notable changes to the rMirror Cloud project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

### Upcoming Milestones

**Mac Agent** (In Progress)
- Local reMarkable tablet sync
- Python background service
- File watching and automatic upload

**Web Dashboard** (Planned)
- Notebook browsing interface
- Todo management UI
- Integration configuration
- Search and filtering

---

## Version History

- **Unreleased** - Current development version with todo extraction and Notion integration
- **0.1.0** - Initial development phase with core backend and OCR processing

---

## Notes

This changelog documents the major features and changes to the rMirror Cloud project. For detailed commit history, see the [Git log](https://github.com/gottino/rmirror-cloud/commits/main).

For upcoming features and planned work, see the [Roadmap](README.md#-roadmap) in the main README.
