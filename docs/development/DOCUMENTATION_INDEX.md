# rMirror Cloud Backend - Documentation Index

Welcome to the rMirror Cloud Backend documentation! This index helps you find the right documentation for your needs.

## Quick Start

**New to rMirror?** Start here:
1. [Backend README](../../backend/README.md) - Overview and quick start
2. [Setup Guide](setup.md) - Local development setup
3. [CHANGELOG](../../CHANGELOG.md) - What's new in the project

## Documentation by Role

### For Developers

#### Getting Started
- [Backend README](../../backend/README.md) - Features, installation, and quick start
- [Setup Guide](setup.md) - Detailed development environment setup
- [Project Structure](../../backend/README.md#project-structure) - Codebase organization

#### Authentication & Security
- [Authentication & Security Guide](AUTHENTICATION_SECURITY.md) - OAuth, Clerk, and development mode
- [Clerk Setup](../../backend/CLERK_SETUP.md) - Clerk authentication configuration
- **Key Topics:**
  - Production OAuth with Clerk
  - Local development mode (DEBUG-gated)
  - Token management and security
  - Webhook signature verification

#### Core Features
- [OCR Deduplication Guide](OCR_DEDUPLICATION.md) - SHA-256 file hashing system
  - How deduplication works
  - Performance benefits (90% cost reduction)
  - Hash calculation and storage
- [Initial Sync Feature](../../agent/INITIAL_SYNC_FEATURE.md) - Bulk upload functionality
  - Web UI and API usage
  - Configuration options
  - Use cases (first-time setup, catch-up)

#### Database & Operations
- [PostgreSQL Migration Guide](../../backend/scripts/POSTGRES_MIGRATION.md) - SQLite to PostgreSQL migration
  - Automated migration script
  - Manual step-by-step process
  - Rollback plan
- [Utilities Guide](UTILITIES_GUIDE.md) - All utility scripts
  - Hash backfilling tools
  - Coverage reporting
  - Sync integrity checks
  - Database maintenance

#### API Documentation
- [API Reference](../api/backend-api.md) - Complete endpoint documentation
- [Backend README - API Overview](../../backend/README.md#api-overview) - Quick API reference
- **Key Endpoints:**
  - Authentication (`/v1/auth/*`)
  - Notebooks (`/v1/notebooks/*`)
  - Processing (`/v1/processing/*`)
  - Todos (`/v1/todos/*`)
  - Sync (`/v1/sync/*`)

#### Deployment
- [Deployment Guide](../deployment/hetzner.md) - Production deployment
- [GitHub Actions](../deployment/github-actions.md) - CI/CD automation
- [Deployment Checklist](../../backend/scripts/deployment_checklist.md) - Pre-deployment verification

---

### For DevOps / Operations

#### Production Setup
- [Deployment Guide](../deployment/hetzner.md) - Hetzner Cloud deployment
- [PostgreSQL Migration](../../backend/scripts/POSTGRES_MIGRATION.md) - Database migration
- [GitHub Actions](../deployment/github-actions.md) - Automated deployments

#### Database Management
- [PostgreSQL Migration Guide](../../backend/scripts/POSTGRES_MIGRATION.md) - Migration process
- [Utilities Guide - Database Maintenance](UTILITIES_GUIDE.md#database-maintenance) - Maintenance tasks
- **Key Operations:**
  - Automated SQLite → PostgreSQL migration
  - Database backups and restoration
  - Schema migrations with Alembic
  - Performance tuning

#### Monitoring & Maintenance
- [Utilities Guide](UTILITIES_GUIDE.md) - All maintenance scripts
  - Hash coverage monitoring
  - Sync integrity verification
  - Missing pages detection
- **Regular Tasks:**
  - Weekly hash coverage reports
  - Monthly sync integrity checks
  - Database size monitoring
  - S3 storage cleanup

#### Security
- [Authentication & Security](AUTHENTICATION_SECURITY.md) - Security architecture
- [Security Checklist](AUTHENTICATION_SECURITY.md#security-checklist) - Pre/post-deployment checks
- **Key Areas:**
  - Clerk OAuth configuration
  - Environment variable management
  - Webhook security
  - Token management

---

### For End Users

#### Getting Started with rMirror
- [Main README](../../README.md) - Project overview
- [CHANGELOG](../../CHANGELOG.md) - Recent updates and features

#### Using the Mac Agent
- [Initial Sync Feature](../../agent/INITIAL_SYNC_FEATURE.md) - Uploading all notebooks
  - When to use Initial Sync
  - Web UI instructions
  - Configuration options

#### Troubleshooting
- [OCR Deduplication - Troubleshooting](OCR_DEDUPLICATION.md#troubleshooting) - OCR issues
- [Authentication - Troubleshooting](AUTHENTICATION_SECURITY.md#troubleshooting) - Login issues
- [Utilities Guide - Troubleshooting](UTILITIES_GUIDE.md#troubleshooting) - Script issues

---

## Documentation by Feature

### OCR & Processing
- **[OCR Deduplication Guide](OCR_DEDUPLICATION.md)** - Complete deduplication documentation
  - How it works
  - Database schema
  - API endpoint
  - Hash backfilling utilities
  - Coverage reporting
  - Performance metrics
- **[Processing API](../../backend/README.md#api-overview)** - OCR endpoint reference

### Authentication & Users
- **[Authentication & Security Guide](AUTHENTICATION_SECURITY.md)** - Complete auth documentation
  - Production Clerk OAuth
  - Local development mode
  - Endpoint protection
  - Security best practices
- **[Clerk Setup](../../backend/CLERK_SETUP.md)** - Clerk configuration

### Database & Migrations
- **[PostgreSQL Migration](../../backend/scripts/POSTGRES_MIGRATION.md)** - Complete migration guide
  - Quick start (automated)
  - Manual step-by-step
  - Rollback procedures
  - Performance tuning
- **[Database Migrations](../../backend/README.md#database-migrations)** - Alembic usage

### Sync & Upload
- **[Initial Sync Feature](../../agent/INITIAL_SYNC_FEATURE.md)** - Bulk upload documentation
  - Backend implementation
  - Frontend UI
  - Usage scenarios
  - Configuration
- **[Sync Integrity Tools](UTILITIES_GUIDE.md#sync-integrity-tools)** - Verification utilities

### Utilities & Tools
- **[Utilities Guide](UTILITIES_GUIDE.md)** - Complete utilities documentation
  - OCR hash management
  - Sync integrity tools
  - Database maintenance
  - Best practices

---

## Documentation by Task

### "I want to set up local development"
1. [Backend README - Quick Start](../../backend/README.md#quick-start)
2. [Setup Guide](setup.md)
3. [Authentication & Security - Local Development](AUTHENTICATION_SECURITY.md#scenario-1-local-development)

### "I want to deploy to production"
1. [Deployment Guide](../deployment/hetzner.md)
2. [GitHub Actions](../deployment/github-actions.md)
3. [Security Checklist](AUTHENTICATION_SECURITY.md#security-checklist)
4. [Deployment Checklist](../../backend/scripts/deployment_checklist.md)

### "I want to migrate from SQLite to PostgreSQL"
1. [PostgreSQL Migration - Quick Start](../../backend/scripts/POSTGRES_MIGRATION.md#quick-start-automated)
2. [Full Migration Guide](../../backend/scripts/POSTGRES_MIGRATION.md)
3. [Database Migrations](../../backend/README.md#database-migrations)

### "I want to improve OCR performance"
1. [OCR Deduplication Guide](OCR_DEDUPLICATION.md)
2. [Hash Backfilling](UTILITIES_GUIDE.md#backfill_page_hashespy)
3. [Coverage Reporting](UTILITIES_GUIDE.md#hash_coverage_reportpy)

### "I want to verify sync integrity"
1. [Hash Coverage Report](UTILITIES_GUIDE.md#hash_coverage_reportpy)
2. [Missing Pages Summary](UTILITIES_GUIDE.md#show_missing_pages_summarypy)
3. [Database vs Content Comparison](UTILITIES_GUIDE.md#check_content_vs_dbpy)

### "I want to upload all my notebooks at once"
1. [Initial Sync Feature](../../agent/INITIAL_SYNC_FEATURE.md)
2. [Initial Sync - Usage](../../agent/INITIAL_SYNC_FEATURE.md#usage)
3. [Initial Sync - Use Cases](../../agent/INITIAL_SYNC_FEATURE.md#use-cases)

### "I'm getting authentication errors"
1. [Authentication Troubleshooting](AUTHENTICATION_SECURITY.md#troubleshooting)
2. [Clerk Setup](../../backend/CLERK_SETUP.md)
3. [Security Checklist](AUTHENTICATION_SECURITY.md#security-checklist)

---

## Recent Updates (December 2025)

### New Documentation
- ✨ [OCR Deduplication Guide](OCR_DEDUPLICATION.md) - Complete hash-based deduplication system
- ✨ [Utilities Guide](UTILITIES_GUIDE.md) - All utility scripts with examples
- ✨ [Authentication & Security](AUTHENTICATION_SECURITY.md) - OAuth and development mode
- ✨ [PostgreSQL Migration](../../backend/scripts/POSTGRES_MIGRATION.md) - Automated migration guide
- ✨ [Initial Sync Feature](../../agent/INITIAL_SYNC_FEATURE.md) - Bulk upload documentation

### Updated Documentation
- 📝 [CHANGELOG](../../CHANGELOG.md) - December 2025 updates
- 📝 [Backend README](../../backend/README.md) - New features and utilities section
- 📝 All documentation cross-references updated

### Key Features Documented
- OCR deduplication with SHA-256 file hashing
- Hash backfilling and coverage tools
- Initial sync for bulk uploads
- PostgreSQL migration automation
- Authentication security improvements
- Development mode for local testing

---

## Documentation Format Guide

### For Technical Writers

**File Organization:**
- `/backend/*.md` - Backend-specific configuration documentation
- `/backend/scripts/*.md` - Script and utility documentation
- `/agent/*.md` - Agent-specific documentation
- `/docs/development/*.md` - Development guides and tutorials
- `/docs/deployment/*.md` - Deployment guides
- `/docs/api/*.md` - API reference documentation

**Cross-Referencing:**
- Use relative paths: `[Link](../docs/file.md)`
- Include section anchors: `[Link](file.md#section)`
- Verify all links work before committing

**Documentation Standards:**
- Include table of contents for docs >500 lines
- Use code blocks with language identifiers
- Include examples for all features
- Add troubleshooting sections
- Cross-reference related documentation

---

## Contributing to Documentation

### Adding New Documentation

1. **Determine location:**
   - Backend config → `/backend/FEATURE_NAME.md`
   - Utility/script → `/backend/scripts/SCRIPT_NAME.md`
   - Agent feature → `/agent/FEATURE_NAME.md`
   - Development guide → `/docs/development/guide.md`
   - Deployment guide → `/docs/deployment/guide.md`
   - API reference → `/docs/api/reference.md`

2. **Follow template:**
   - Overview section
   - How it works
   - Usage examples
   - Configuration
   - Troubleshooting
   - Related documentation links

3. **Update this index:**
   - Add to relevant sections
   - Update "Recent Updates"
   - Add cross-references

4. **Update main README:**
   - Add to Documentation section
   - Link from relevant feature descriptions

### Reviewing Documentation

**Checklist:**
- [ ] All code examples tested and working
- [ ] All links verified and working
- [ ] Consistent terminology throughout
- [ ] Includes troubleshooting section
- [ ] Cross-references related docs
- [ ] Added to DOCUMENTATION_INDEX.md
- [ ] Updated in main README if major feature

---

## Getting Help

### Documentation Issues
- Missing documentation? [Open an issue](https://github.com/gottino/rmirror-cloud/issues)
- Found an error? [Submit a PR](https://github.com/gottino/rmirror-cloud/pulls)
- Need clarification? Check troubleshooting sections first

### Technical Support
- Backend issues → [Backend README](../../backend/README.md)
- Authentication issues → [Authentication Guide](AUTHENTICATION_SECURITY.md)
- Database issues → [Utilities Guide](UTILITIES_GUIDE.md)
- Deployment issues → [Deployment Guide](../deployment/hetzner.md)

---

## External Resources

### Technologies Used
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Clerk Documentation](https://clerk.com/docs)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)

### Related Projects
- [reMarkable Tablet](https://remarkable.com/)
- [Claude AI](https://www.anthropic.com/claude)
- [Notion API](https://developers.notion.com/)

---

**Last Updated:** December 26, 2025

**Documentation Version:** 2.0 (December 2025 Update)

For the complete changelog, see [CHANGELOG.md](../../CHANGELOG.md).
