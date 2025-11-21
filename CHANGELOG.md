# Changelog

All notable changes to the rMirror Cloud project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

#### Mac Agent (2025-11-21)
- Removed redundant OCR trigger call causing 404 errors (OCR is automatic in /v1/processing/rm-file)
- Fixed async function handling in Flask web UI routes

- Made database migration idempotent to handle partial failures (2025-11-15)
- Added server_default for boolean columns in migration (2025-11-15)
- Fixed sudoers wildcards for systemctl flags (2025-11-10)
- Added both `/usr/bin/systemctl` and `/bin/systemctl` paths to sudoers (2025-11-10)
- Updated git pull to occur before deployment (2025-11-10)
- Auto-detect Poetry installation path in deploy script (2025-11-10)
- Updated Poetry install command for modern Poetry versions (2025-11-10)

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
