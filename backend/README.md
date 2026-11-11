# rMirror Cloud Backend

FastAPI backend for rMirror Cloud - a cloud service that brings your reMarkable tablet notes to the cloud with OCR, todo extraction, and integrations with Notion and other services.

## Features

- **Notebook Management** - Store and manage reMarkable notebooks in the cloud
- **OCR Processing** - Extract text from handwritten notes using Google Gemini Vision
- **OCR Deduplication** - SHA-256 file hashing (`pages.file_hash`) to prevent re-processing unchanged files
- **Todo Extraction** - Automatically detect and extract todo items from checkbox patterns
- **Notion Integration** - Sync notebooks to Notion with markdown formatting
- **Initial Sync** - Bulk upload functionality for catch-up scenarios
- **PostgreSQL Support** - Automated migration from SQLite to PostgreSQL
- **RESTful API** - Comprehensive API for all features
- **Clerk Authentication** - Clerk session tokens, plus 30-day agent tokens (`POST /v1/auth/agent-token`)
- **Database Migrations** - Alembic for schema version control

## Quick Start

### Prerequisites

- Python 3.11+
- Poetry for dependency management
- SQLite (development) or PostgreSQL (production)

### Installation

```bash
# Clone the repository
git clone https://github.com/gottino/rmirror-cloud.git
cd rmirror-cloud/backend

# Install dependencies
poetry install

# Create .env file
cp .env.example .env
# Edit .env with your configuration

# Run database migrations
poetry run alembic upgrade head

# Start development server
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

Interactive API documentation:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=app --cov-report=html

# Run specific test file
poetry run pytest tests/test_quota_service.py
```

## Environment Variables

Create a `.env` file in the backend directory:

```bash
# Database (SQLite for development, PostgreSQL for production)
DATABASE_URL=sqlite:///./rmirror.db
# DATABASE_URL=postgresql://user:password@localhost:5432/rmirror

# Security
SECRET_KEY=your-secret-key-here
ACCESS_TOKEN_EXPIRE_MINUTES=10080

# Google Gemini (for OCR)
GOOGLE_AI_API_KEY=your-google-ai-api-key

# Clerk authentication
CLERK_SECRET_KEY=your-clerk-secret-key
CLERK_JWKS_URL=https://your-instance.clerk.accounts.dev/.well-known/jwks.json
CLERK_WEBHOOK_SECRET=your-clerk-webhook-secret

# Notion Integration (optional)
NOTION_CLIENT_ID=your-notion-client-id
NOTION_CLIENT_SECRET=your-notion-client-secret
NOTION_REDIRECT_URI=https://your-domain.com/v1/integrations/notion/callback

# S3 Storage (optional, for file storage)
S3_ENDPOINT=https://s3.amazonaws.com
S3_BUCKET=rmirror-files
S3_ACCESS_KEY=your-access-key
S3_SECRET_KEY=your-secret-key
```

**Local development without Clerk:** with no `CLERK_JWKS_URL`, set `ALLOW_UNVERIFIED_CLERK_TOKENS=true` (and `ALLOW_UNSIGNED_WEBHOOKS=true` if you post webhooks without `CLERK_WEBHOOK_SECRET`).
These flags work only with a SQLite `DATABASE_URL`; the API refuses to start with them on PostgreSQL. `DEBUG` only changes log verbosity.

## Documentation

### Quick References
- **[📖 Complete Documentation](../docs/)** - Full project documentation
- **[CHANGELOG](../CHANGELOG.md)** - Complete project changelog with all changes

### Guides
- **[Authentication & Security](../docs/development/AUTHENTICATION_SECURITY.md)** - Clerk authentication and development mode
- **[PostgreSQL Migration Guide](scripts/POSTGRES_MIGRATION.md)** - Automated PostgreSQL migration
- **[Initial Sync Feature](../agent/INITIAL_SYNC_FEATURE.md)** - Bulk upload documentation

### General Documentation
- **[API Reference](../docs/api/backend-api.md)** - Complete API endpoint documentation
- **[Deployment Guide](../docs/deployment/hetzner.md)** - Production deployment on Hetzner
- **[GitHub Actions](../docs/deployment/github-actions.md)** - Automated deployment setup
- **[Clerk Setup](CLERK_SETUP.md)** - Clerk authentication configuration

## Project Structure

```
backend/
├── app/
│   ├── api/              # API endpoints
│   │   ├── auth.py       # Agent token endpoint (POST /auth/agent-token)
│   │   ├── users.py      # User management
│   │   ├── notebooks.py  # Notebook CRUD
│   │   ├── processing.py # OCR processing
│   │   ├── todos.py      # Todo management
│   │   ├── integrations.py # External integrations
│   │   └── sync.py       # Sync management
│   ├── models/           # SQLAlchemy models
│   │   ├── user.py
│   │   ├── notebook.py
│   │   ├── page.py
│   │   ├── todo.py
│   │   └── ...
│   ├── processors/       # Business logic
│   │   ├── todo_extractor.py
│   │   ├── intelligent_todo_deduplication.py
│   │   └── ...
│   ├── integrations/     # External service integrations
│   │   ├── notion_sync.py
│   │   └── notion_markdown.py
│   ├── auth/            # Authentication logic
│   ├── core/            # Core utilities
│   └── main.py          # FastAPI application
├── alembic/             # Database migrations
├── tests/               # Test suite
├── scripts/             # Deployment and PostgreSQL migration scripts
└── pyproject.toml       # Poetry dependencies
```

## API Overview

### Authentication
Login is handled by Clerk. The password login/register endpoints were removed.
- `POST /v1/auth/agent-token` - Exchange a Clerk session token for a 30-day agent token

### Notebooks
- `GET /v1/notebooks/` - List user's notebooks
- `GET /v1/notebooks/uuid/{uuid}` - Get notebook by UUID
- `GET /v1/notebooks/tree` - Notebook/folder tree
- `GET /v1/notebooks/{id}` - Get notebook with its pages
- `GET /v1/notebooks/{id}/export?format=markdown|pdf` - Export a notebook

### Todos
- `GET /v1/todos/` - List todos (with filters)
- `GET /v1/todos/{id}` - Get specific todo
- `PATCH /v1/todos/{id}` - Update todo
- `DELETE /v1/todos/{id}` - Delete todo
- `POST /v1/todos/extract` - Extract todos from notebooks
- `GET /v1/todos/stats/summary` - Get statistics

### Integrations
- `GET /v1/integrations/` - List configured integrations
- `GET /v1/integrations/notion/oauth/authorize` - Start Notion OAuth
- `POST /v1/integrations/{target_name}/test` - Test an integration connection
- `POST /v1/sync/trigger` - Queue a sync

See the [API Reference](../docs/api/backend-api.md) or `/docs` on a running server for complete endpoint documentation.

## Utility Scripts

### PostgreSQL Migration

**Automated migration from SQLite:**
```bash
# SSH to production
ssh deploy@your-server.com
cd /var/www/rmirror-cloud/backend

# Run automated migration
sudo -E ./scripts/migrate_to_postgres.sh
```

See [PostgreSQL Migration Guide](scripts/POSTGRES_MIGRATION.md) for details.

## Development

### Database Migrations

```bash
# Create a new migration
poetry run alembic revision --autogenerate -m "Description"

# Apply migrations
poetry run alembic upgrade head

# Rollback one migration
poetry run alembic downgrade -1

# View migration history
poetry run alembic history
```

### Testing Locally

```bash
# Start the server
poetry run uvicorn app.main:app --reload

# In another terminal, check the server
curl http://localhost:8000/health
```

Authenticated endpoints need a Clerk session token (or an agent token); see [Clerk Setup](CLERK_SETUP.md).

## Production Deployment

See the [Deployment Guide](../docs/deployment/hetzner.md) for complete production deployment instructions.

Quick production checklist:
- [ ] Set strong `SECRET_KEY` in production .env
- [ ] Use PostgreSQL instead of SQLite (recommended)
- [ ] Configure proper CORS origins
- [ ] Set up SSL/TLS certificates
- [ ] Configure automated backups
- [ ] Set up monitoring and logging
- [ ] Use systemd or supervisor for process management

Automated deployment via [GitHub Actions](../docs/deployment/github-actions.md) is configured for this project.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`poetry run pytest`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## License

This project is proprietary software. All rights reserved.

## Support

For issues or questions:
- GitHub Issues: https://github.com/gottino/rmirror-cloud/issues
- Email: support@rmirror.cloud

---

Built with FastAPI, SQLAlchemy, and Google Gemini.
