# rMirror Cloud Documentation

Welcome to the rMirror Cloud documentation! This guide will help you understand, develop, and deploy the rMirror Cloud platform.

## What is rMirror Cloud?

rMirror Cloud is a comprehensive cloud service that brings your reMarkable tablet notes to the cloud with OCR processing, intelligent todo extraction, and seamless integrations with services like Notion.

**Key Features:**
- 📓 **Cloud Notebook Storage** - Sync and store your reMarkable notebooks
- 🔍 **OCR Processing** - Extract text from handwritten notes using Claude Vision API
- ✅ **Smart Todo Extraction** - Automatically detect and manage checkbox todo items
- 🔄 **Notion Integration** - Full production sync with metadata-only mode for speed
- 📊 **Quota Management** - Free tier (30 pages/month) with graceful degradation
- 🔐 **Clerk Authentication** - Secure OAuth via Google, GitHub, and email
- 📱 **Mac Agent** - Local agent for seamless reMarkable sync with menu bar UI
- 🌐 **RESTful API** - Complete API for all platform features

## Project Components

The rMirror Cloud platform consists of three main components:

1. **Backend** (`/backend`) - FastAPI-based REST API and core services
2. **Agent** (`/agent`) - macOS application for local reMarkable tablet sync
3. **Dashboard** (`/dashboard`) - Next.js web-based user interface

## Documentation Structure

### Getting Started

- **[Architecture Overview](architecture.md)** - System architecture and component relationships
- **[Development Setup](development/setup.md)** - Set up your development environment
- **[Quick Start Guide](#quick-start)** - Get up and running in 5 minutes
- **[Documentation Index](development/DOCUMENTATION_INDEX.md)** - Complete documentation catalog

### Development Guides

- **[Development Setup](development/setup.md)** - Detailed development environment setup
- **[OCR Deduplication Guide](development/OCR_DEDUPLICATION.md)** - SHA-256 file hashing system for OCR cost reduction
- **[Utilities Guide](development/UTILITIES_GUIDE.md)** - Database utilities, hash backfilling, and maintenance tools
- **[Authentication & Security](development/AUTHENTICATION_SECURITY.md)** - OAuth with Clerk, development mode, security best practices
- **[Contributing Guidelines](../CONTRIBUTING.md)** - How to contribute to the project

### API Documentation

- **[Backend API Reference](api/backend-api.md)** - Complete REST API endpoint documentation
  - Authentication endpoints
  - Notebook management (including Initial Sync)
  - Processing & OCR (with deduplication)
  - Todo extraction and management
  - Agent management
  - Integrations (Notion, etc.)
  - Sync operations

### Deployment Guides

- **[Hetzner Deployment](deployment/hetzner.md)** - Production deployment on Hetzner Cloud
- **[GitHub Actions CI/CD](deployment/github-actions.md)** - Automated deployment setup
- **[Resend Email Setup](deployment/RESEND_SETUP.md)** - Configure Resend for transactional emails
- **[Deployment Automation](deployment/automation.md)** - Scripts and automation tools

### Architecture

- **[Architecture Overview](architecture.md)** - System design and component relationships
- **[Project Context](../CONTEXT.md)** - Project history and background

---

## Quick Start

### For End Users

1. **Sign up** at https://rmirror.io
2. **Download the agent** from the dashboard (macOS only)
3. **Connect your reMarkable** and start syncing

### For Developers

#### Prerequisites

- Python 3.11+
- Poetry for Python dependency management
- Node.js 18+ (for dashboard development)
- Git
- (Optional) Docker for containerized deployment

#### 1. Clone the Repository

```bash
git clone https://github.com/gottino/rmirror-cloud.git
cd rmirror-cloud
```

#### 2. Backend Setup

```bash
cd backend

# Install dependencies
poetry install

# Create environment file
cp .env.example .env
# Edit .env with your configuration (especially CLAUDE_API_KEY and CLERK_SECRET_KEY)

# Run database migrations
poetry run alembic upgrade head

# Start the development server
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at http://localhost:8000

**Interactive API docs:** http://localhost:8000/docs

#### 3. Quick Development Start

Use the `/dev` slash command in Claude Code for automated local setup:

```bash
# From repository root with Claude Code
/dev
# This starts backend, dashboard, and agent in parallel
```

#### 4. Dashboard Setup (Optional)

```bash
cd dashboard

# Install dependencies
npm install

# Create environment file
cp .env.example .env.local
# Configure NEXT_PUBLIC_API_URL and Clerk keys

# Start development server
npm run dev
```

Dashboard available at http://localhost:3000

---

## Component Documentation

### Backend

The backend is a FastAPI application that provides the core API services.

**Location:** `/backend`

**Key Technologies:**
- FastAPI - Modern Python web framework
- SQLAlchemy - ORM for database access
- Alembic - Database migrations
- Claude Vision API - OCR processing
- Notion API - Integration
- Clerk - Authentication
- Resend - Email notifications

**Documentation:**
- [Backend README](../backend/README.md) - Component overview
- [API Reference](api/backend-api.md) - Complete API documentation
- [Setup Guide](development/setup.md) - Development setup

**Test Scripts:**
- `test_todo_extraction.py` - Test todo extraction feature
- `test_notion_sync.py` - Test Notion integration

### Agent (macOS)

The agent runs locally on macOS and syncs reMarkable tablets with the cloud backend.

**Location:** `/agent`

**Status:** 🟢 Production Ready - v1.4.1

**Key Features:**
- Menu bar app with real-time status
- Automatic file watching with watchdog library
- Real-time sync to cloud backend
- Intelligent sync queue with batching and deduplication
- Exponential backoff retry logic for failed uploads
- Web UI for configuration and monitoring (localhost:9090)
- Quota display with color-coded status (green/orange/red)
- CLI interface with foreground/background modes
- Support for .rm, .metadata, and .content files
- Secure token storage via macOS keychain

**Installation:**

For end users:
1. Download the `.app` bundle from https://rmirror.io after signup
2. Move to Applications folder
3. Launch and sign in

For developers:
```bash
cd agent
poetry install
./build_macos.sh  # Build .app bundle
```

See [agent/README.md](../agent/README.md) for detailed setup instructions.

### Dashboard (Web)

The dashboard provides a web-based interface for managing notebooks, todos, and integrations.

**Location:** `/dashboard`

**Status:** 🟢 Production Ready

**Deployed at:** https://rmirror.io (Vercel)

**Key Technologies:**
- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- Clerk Authentication
- React Server Components

**Features:**
- **Notebook Browsing** - View all synced notebooks with search and filtering
- **Page Viewing** - View individual pages with OCR text and PDF preview
- **Quota Management** - Real-time quota display with color-coded status
  - Green: < 75% used
  - Orange: 75-100% used
  - Red: 100% used (shows upgrade CTA)
- **Integration Management** - Connect and configure Notion integration
- **Authentication** - OAuth via Google, GitHub, or email (Clerk)
- **Responsive Design** - Works on desktop and mobile
- **Moleskine-inspired UI** - Warm, paper-like aesthetic

**Development:**
```bash
cd dashboard
npm install
npm run dev  # Runs on localhost:3000
```

See [dashboard/README.md](../dashboard/README.md) for detailed documentation.

---

## API Overview

The rMirror Cloud backend provides a comprehensive REST API. Here's a quick overview:

### Authentication
```bash
POST /v1/auth/login        # Get access token
POST /v1/auth/register     # Create new user
```

### Notebooks
```bash
GET    /v1/notebooks/                    # List all notebooks
GET    /v1/notebooks/uuid/{uuid}         # Get notebook by UUID
GET    /v1/notebooks/{id}/pages          # Get notebook pages
GET    /v1/notebooks/{id}/content        # Get as markdown
```

### Todos
```bash
GET    /v1/todos/                        # List todos (with filters)
POST   /v1/todos/extract                 # Extract from notebooks
PATCH  /v1/todos/{id}                    # Update todo
DELETE /v1/todos/{id}                    # Delete todo
GET    /v1/todos/stats/summary           # Get statistics
```

### Integrations
```bash
POST   /v1/integrations/notion           # Configure Notion
GET    /v1/integrations/notion/test      # Test connection
POST   /v1/sync/notebook/{id}            # Sync to Notion
```

### Quota Management
```bash
GET    /v1/quota/usage                   # Get quota usage
GET    /v1/quota/status                  # Get quota status
POST   /v1/quota/consume                 # Consume quota (internal)
```

**Quota Behavior:**
- Free tier: 30 OCR pages per month
- Uploads accepted even when quota exhausted (OCR deferred)
- Pages set to `PENDING_QUOTA` status when quota exceeded
- Email notifications at 90% and 100% usage
- HTTP 402 returned for operations requiring quota

See the [Complete API Reference](api/backend-api.md) for detailed documentation.

---

## Architecture

The rMirror Cloud platform follows a client-server architecture:

```
┌─────────────────┐
│  reMarkable     │
│    Tablet       │
└────────┬────────┘
         │
         │ USB/WiFi Sync
         ▼
┌─────────────────┐         HTTPS         ┌─────────────────┐
│   Mac Agent     │◄──────────────────────►│  Cloud Backend  │
│   (Local)       │    Clerk Auth          │   (FastAPI)     │
│  - Menu bar UI  │    Quota checks        │  - OCR + Claude │
│  - File watcher │                        │  - PostgreSQL   │
└─────────────────┘                        │  - Quota mgmt   │
         ▲                                 └────────┬────────┘
         │                                          │
         │                                          │
         │       ┌──────────────────────────────────┼────────┐
         │       │                                  │        │
         │       ▼                                  ▼        ▼
         │ ┌─────────────────┐            ┌──────────────────┐
         └─┤  Web Dashboard  │            │   Integrations   │
           │   (Next.js)     │            │  - Notion        │
           │  - Vercel       │            │  - Readwise (*)  │
           └─────────────────┘            └──────────────────┘
```

*(\*) = Planned*

See [architecture.md](architecture.md) for detailed architecture documentation.

---

## Development Workflow

### Using Claude Code Slash Commands

This project includes custom slash commands for common workflows:

- `/dev` - Start all services (backend, dashboard, agent) for local development
- `/test-backend` - Run backend tests with coverage
- `/test-agent` - Run agent tests
- `/migrate` - Create and apply database migrations
- `/commit-push` - Commit and push changes with conventional commits
- `/create-task` - Create tasks in project management

### 1. Feature Development

```bash
# Create feature branch
git checkout -b feature/your-feature-name

# Start all services with Claude Code
/dev

# Or manually start individual components:
# Terminal 1 - Backend
cd backend
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 - Dashboard (optional)
cd dashboard
npm run dev

# Terminal 3 - Agent (optional)
cd agent
poetry run python -m app.main --foreground --debug

# Run tests
poetry run pytest  # Backend
npm test          # Dashboard

# Commit changes
git add .
git commit -m "feat: add your feature"
```

### 2. Database Migrations

```bash
# Using Claude Code slash command
/migrate

# Or manually:
cd backend

# Create migration after model changes
poetry run alembic revision --autogenerate -m "Description"

# Review the generated migration in alembic/versions/

# Apply migration
poetry run alembic upgrade head

# CRITICAL: Always use `poetry run alembic` (never bare `alembic`)
```

### 3. Deployment

The project uses GitHub Actions for automated deployment to production:

1. Push to `main` branch
2. GitHub Actions runs tests
3. Deploys to Hetzner Cloud automatically

See [GitHub Actions Deployment](deployment/github-actions.md) for details.

---

## Environment Configuration

### Development (.env)

```bash
# Database (SQLite for local, PostgreSQL for production)
DATABASE_URL=sqlite:///./rmirror.db

# Security
SECRET_KEY=your-dev-secret-key
ACCESS_TOKEN_EXPIRE_MINUTES=10080
DEBUG=true  # Enables development mode authentication

# Claude API (for OCR)
CLAUDE_API_KEY=your-claude-api-key

# Clerk Authentication (get from https://clerk.com)
CLERK_SECRET_KEY=sk_test_your_dev_key
CLERK_WEBHOOK_SECRET=whsec_your_webhook_secret
CLERK_PUBLISHABLE_KEY=pk_test_your_publishable_key  # For dashboard

# Email Service (Resend)
RESEND_API_KEY=re_your_dev_api_key
RESEND_FROM_EMAIL=onboarding@resend.dev  # Use this for testing

# Notion (optional for testing)
NOTION_CLIENT_ID=your-client-id
NOTION_CLIENT_SECRET=your-client-secret
NOTION_REDIRECT_URI=http://localhost:8000/v1/integrations/notion/callback

# Quota Settings (optional, defaults shown)
DEFAULT_QUOTA_LIMIT=30  # Free tier limit
QUOTA_WARNING_THRESHOLD=0.9  # Send warning at 90%
```

### Production (.env)

```bash
# Database (PostgreSQL for production)
DATABASE_URL=postgresql://user:password@localhost:5432/rmirror

# Security (use strong random key)
SECRET_KEY=production-secret-key-min-32-chars
ACCESS_TOKEN_EXPIRE_MINUTES=10080
DEBUG=false  # CRITICAL: Must be false in production

# Claude API (for OCR)
CLAUDE_API_KEY=your-production-claude-api-key

# Clerk Authentication
CLERK_SECRET_KEY=sk_live_your_production_key
CLERK_WEBHOOK_SECRET=whsec_your_webhook_secret
CLERK_PUBLISHABLE_KEY=pk_live_your_publishable_key

# Email Service (Resend)
RESEND_API_KEY=re_your_production_api_key
RESEND_FROM_EMAIL=noreply@rmirror.io  # Use verified domain

# Notion
NOTION_CLIENT_ID=your-production-client-id
NOTION_CLIENT_SECRET=your-production-client-secret
NOTION_REDIRECT_URI=https://api.rmirror.io/v1/integrations/notion/callback

# Quota Settings
DEFAULT_QUOTA_LIMIT=30  # Free tier
QUOTA_WARNING_THRESHOLD=0.9  # Send warning at 90%
```

**See also:**
- [Resend Setup Guide](deployment/RESEND_SETUP.md) - Complete Resend configuration
- [Authentication & Security Guide](development/AUTHENTICATION_SECURITY.md) - Clerk setup and security

---

## Testing

### Backend Tests

```bash
cd backend

# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=app --cov-report=html

# Run specific test file
poetry run pytest tests/test_todos.py

# Run integration tests
poetry run python test_todo_extraction.py
poetry run python test_notion_sync.py
```

---

## Troubleshooting

### Common Issues

**Issue:** Database migration errors
```bash
# Solution: Check current migration status
poetry run alembic current

# Downgrade and reapply
poetry run alembic downgrade -1
poetry run alembic upgrade head
```

**Issue:** OCR not working
- Verify `CLAUDE_API_KEY` is set correctly in .env
- Check Claude API quota and rate limits
- Review logs: `tail -f backend/logs/app.log`

**Issue:** Notion sync failing
- Test connection: `GET /v1/integrations/notion/test`
- Verify OAuth tokens haven't expired
- Check Notion API permissions

---

## Support & Contributing

### Getting Help

- 📖 Read the docs (you're here!)
- 🐛 [Report bugs](https://github.com/gottino/rmirror-cloud/issues)
- 💬 [Discussions](https://github.com/gottino/rmirror-cloud/discussions)
- 📧 Email: support@rmirror.cloud

### Contributing

We welcome contributions! See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines.

Quick contribution workflow:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

---

## License

This project is proprietary software. All rights reserved.

---

## Project Status

🟢 **Backend API** - Production ready (deployed on Hetzner)
🟢 **macOS Agent** - Production ready v1.4.1 (available at https://rmirror.io)
🟢 **Web Dashboard** - Production ready (deployed on Vercel)

**Recent Updates (January 2026):**
- ✅ Quota management system with graceful degradation
- ✅ Email notifications (90% warning, 100% exceeded)
- ✅ Dashboard quota UI with color-coded status
- ✅ Agent menu bar app with real-time quota display
- ✅ Clerk authentication (OAuth via Google/GitHub)
- ✅ Database-driven deduplication with page_uuid
- ✅ Metadata-only sync (50-100x faster than full sync)

**Coming Soon:**
- 💳 Stripe integration for paid tiers (Phase 2)
- 📚 Readwise integration
- 🔍 Advanced search and filtering

Last updated: January 2026
