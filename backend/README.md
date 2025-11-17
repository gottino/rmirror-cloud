# rMirror Cloud Backend

FastAPI backend for rMirror Cloud - a cloud service that brings your reMarkable tablet notes to the cloud with OCR, todo extraction, and integrations with Notion and other services.

## Features

- **Notebook Management** - Store and manage reMarkable notebooks in the cloud
- **OCR Processing** - Extract text from handwritten notes using Claude Vision API
- **Todo Extraction** - Automatically detect and extract todo items from checkbox patterns
- **Notion Integration** - Sync notebooks to Notion with markdown formatting
- **RESTful API** - Comprehensive API for all features
- **User Authentication** - Secure JWT-based authentication
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
poetry run pytest tests/test_todos.py
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

# Claude API (for OCR)
CLAUDE_API_KEY=your-claude-api-key

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

## Documentation

- **[📖 Complete Documentation](../docs/)** - Full project documentation
- **[API Reference](../docs/api/backend-api.md)** - Complete API endpoint documentation
- **[Setup Guide](../docs/development/setup.md)** - Detailed setup instructions
- **[Deployment Guide](../docs/deployment/hetzner.md)** - Production deployment on Hetzner
- **[GitHub Actions](../docs/deployment/github-actions.md)** - Automated deployment setup

## Project Structure

```
backend/
├── app/
│   ├── api/              # API endpoints
│   │   ├── auth.py       # Authentication endpoints
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
├── scripts/             # Utility scripts
└── pyproject.toml       # Poetry dependencies
```

## API Overview

### Authentication
- `POST /v1/auth/login` - Get access token
- `POST /v1/auth/register` - Create new user

### Notebooks
- `GET /v1/notebooks/` - List user's notebooks
- `GET /v1/notebooks/uuid/{uuid}` - Get notebook by UUID
- `GET /v1/notebooks/{id}/pages` - Get notebook pages
- `GET /v1/notebooks/{id}/content` - Get notebook as markdown

### Todos
- `GET /v1/todos/` - List todos (with filters)
- `GET /v1/todos/{id}` - Get specific todo
- `PATCH /v1/todos/{id}` - Update todo
- `DELETE /v1/todos/{id}` - Delete todo
- `POST /v1/todos/extract` - Extract todos from notebooks
- `GET /v1/todos/stats/summary` - Get statistics

### Integrations
- `POST /v1/integrations/notion` - Configure Notion
- `GET /v1/integrations/notion/test` - Test Notion connection
- `POST /v1/sync/notebook/{id}` - Sync notebook to Notion

See [API_REFERENCE.md](API_REFERENCE.md) for complete endpoint documentation.

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

# In another terminal, test endpoints
# Login and get token
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password"}'

# Use the provided test scripts
poetry run python test_todo_extraction.py
poetry run python test_notion_sync.py
```

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

Built with FastAPI, SQLAlchemy, and Claude AI.
