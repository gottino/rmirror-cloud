# rMirror Cloud Documentation

Welcome to the rMirror Cloud documentation! This guide will help you understand, develop, and deploy the rMirror Cloud platform.

## What is rMirror Cloud?

rMirror Cloud is a comprehensive cloud service that brings your reMarkable tablet notes to the cloud with OCR processing, intelligent todo extraction, and seamless integrations with services like Notion.

**Key Features:**
- 📓 **Cloud Notebook Storage** - Sync and store your reMarkable notebooks
- 🔍 **OCR Processing** - Extract text from handwritten notes using Claude Vision API
- ✅ **Smart Todo Extraction** - Automatically detect and manage checkbox todo items
- 🔄 **Notion Integration** - Sync notebooks to Notion with markdown formatting
- 📱 **Mac Agent** - Local agent for seamless reMarkable sync
- 🌐 **RESTful API** - Complete API for all platform features

## Project Components

The rMirror Cloud platform consists of three main components:

1. **Backend** (`/backend`) - FastAPI-based REST API and core services
2. **Agent** (`/agent`) - Mac application for local reMarkable tablet sync
3. **Dashboard** (`/dashboard`) - Web-based user interface (coming soon)

## Documentation Structure

### Getting Started

- **[Architecture Overview](architecture.md)** - System architecture and component relationships
- **[Development Setup](development/setup.md)** - Set up your development environment
- **[Quick Start Guide](#quick-start)** - Get up and running in 5 minutes

### API Documentation

- **[Backend API Reference](api/backend-api.md)** - Complete REST API endpoint documentation
  - Authentication endpoints
  - Notebook management
  - Todo extraction and management
  - Integrations (Notion, etc.)
  - Sync operations

### Deployment

- **[Hetzner Deployment](deployment/hetzner.md)** - Production deployment on Hetzner Cloud
- **[GitHub Actions CI/CD](deployment/github-actions.md)** - Automated deployment setup
- **[Deployment Automation](deployment/automation.md)** - Scripts and automation tools

### Development

- **[Development Setup](development/setup.md)** - Detailed development environment setup
- **[Contributing Guidelines](../CONTRIBUTING.md)** - How to contribute to the project
- **[Project Context](../CONTEXT.md)** - Project history and context

---

## Quick Start

### Prerequisites

- Python 3.11+
- Poetry for Python dependency management
- Git
- (Optional) Docker for containerized deployment

### 1. Clone the Repository

```bash
git clone https://github.com/gottino/rmirror-cloud.git
cd rmirror-cloud
```

### 2. Backend Setup

```bash
cd backend

# Install dependencies
poetry install

# Create environment file
cp .env.example .env
# Edit .env with your configuration (especially CLAUDE_API_KEY)

# Run database migrations
poetry run alembic upgrade head

# Start the development server
poetry run uvicorn app.main:app --reload
```

The API will be available at http://localhost:8000

**Interactive API docs:** http://localhost:8000/docs

### 3. Create Your First User

```bash
# Register a new user
curl -X POST http://localhost:8000/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "your@email.com",
    "password": "secure-password",
    "full_name": "Your Name"
  }'
```

### 4. Test Todo Extraction

```bash
# Login and get token
TOKEN=$(curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"your@email.com","password":"secure-password"}' \
  | jq -r '.access_token')

# List notebooks
curl http://localhost:8000/v1/notebooks/ \
  -H "Authorization: Bearer $TOKEN"

# Extract todos from a notebook
curl -X POST http://localhost:8000/v1/todos/extract \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"notebook_ids":[1]}'

# View extracted todos
curl http://localhost:8000/v1/todos/ \
  -H "Authorization: Bearer $TOKEN"
```

---

## Component Documentation

### Backend

The backend is a FastAPI application that provides the core API services.

**Location:** `/backend`

**Key Technologies:**
- FastAPI - Modern Python web framework
- SQLAlchemy - ORM for database access
- Alembic - Database migrations
- Claude API - OCR processing
- Notion API - Integration

**Documentation:**
- [Backend README](../backend/README.md) - Component overview
- [API Reference](api/backend-api.md) - Complete API documentation
- [Setup Guide](development/setup.md) - Development setup

**Test Scripts:**
- `test_todo_extraction.py` - Test todo extraction feature
- `test_notion_sync.py` - Test Notion integration

### Agent (Mac)

The agent runs locally on macOS and syncs reMarkable tablets with the cloud backend.

**Location:** `/agent`

**Status:** In development

**Key Features:**
- Automatic reMarkable tablet detection
- File sync to cloud backend
- Background processing
- Native macOS integration

### Dashboard (Web)

The dashboard provides a web-based interface for managing notebooks, todos, and integrations.

**Location:** `/dashboard`

**Status:** Planned

**Planned Features:**
- Notebook browsing and search
- Todo management interface
- Integration configuration
- User settings

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
│   (Local)       │                        │   (FastAPI)     │
└─────────────────┘                        └────────┬────────┘
                                                    │
         ┌──────────────────────────────────────────┼────────┐
         │                                          │        │
         ▼                                          ▼        ▼
┌─────────────────┐                        ┌──────────────────┐
│  Web Dashboard  │                        │   Integrations   │
│   (React)       │                        │  - Notion        │
└─────────────────┘                        │  - Others...     │
                                           └──────────────────┘
```

See [architecture.md](architecture.md) for detailed architecture documentation.

---

## Development Workflow

### 1. Feature Development

```bash
# Create feature branch
git checkout -b feature/your-feature-name

# Make changes to backend
cd backend
poetry run uvicorn app.main:app --reload

# Run tests
poetry run pytest

# Commit changes
git add .
git commit -m "feat: add your feature"
```

### 2. Database Migrations

```bash
cd backend

# Create migration after model changes
poetry run alembic revision --autogenerate -m "Description"

# Review the generated migration in alembic/versions/

# Apply migration
poetry run alembic upgrade head
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
# Database
DATABASE_URL=sqlite:///./rmirror.db

# Security
SECRET_KEY=your-dev-secret-key
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# Claude API
CLAUDE_API_KEY=your-claude-api-key

# Notion (optional for testing)
NOTION_CLIENT_ID=your-client-id
NOTION_CLIENT_SECRET=your-client-secret
```

### Production (.env)

```bash
# Database (PostgreSQL recommended for production)
DATABASE_URL=postgresql://user:password@localhost:5432/rmirror

# Security (use strong random key)
SECRET_KEY=production-secret-key-min-32-chars
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# Claude API
CLAUDE_API_KEY=your-production-claude-api-key

# Notion
NOTION_CLIENT_ID=your-production-client-id
NOTION_CLIENT_SECRET=your-production-client-secret
NOTION_REDIRECT_URI=https://yourdomain.com/v1/integrations/notion/callback
```

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

🟢 **Backend API** - Production ready
🟡 **Mac Agent** - In development
🔴 **Web Dashboard** - Planned

Last updated: November 2025
