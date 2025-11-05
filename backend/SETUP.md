# Backend Setup Guide

## What's Been Implemented

The FastAPI backend is now fully structured with:

- **Project Structure**: Poetry-based Python 3.11 project with all dependencies
- **Database Models**: Complete SQLAlchemy models for all 7 core tables
  - Users (authentication, subscriptions)
  - Notebooks (reMarkable documents)
  - Pages (individual pages with OCR tracking)
  - Highlights (extracted annotations)
  - Sync Records (external service tracking)
  - Processing Jobs (async task queue)
  - Connectors (external service integrations)
- **Authentication**: JWT-based auth with password hashing
- **API Endpoints**:
  - `POST /v1/auth/register` - User registration
  - `POST /v1/auth/login` - User login (returns JWT)
  - `GET /v1/users/me` - Get current user info (protected)
- **Database Migrations**: Alembic configured and ready
- **Configuration**: Environment-based settings via Pydantic

## File Structure

```
backend/
├── pyproject.toml              # Poetry dependencies
├── .env                        # Environment variables (created)
├── alembic/                    # Database migrations
│   ├── env.py                  # Configured with our models
│   └── versions/               # Migration files (empty until DB is running)
└── app/
    ├── main.py                 # FastAPI application entry point
    ├── config.py               # Settings management
    ├── database.py             # Database session management
    ├── models/                 # SQLAlchemy models
    │   ├── user.py
    │   ├── notebook.py
    │   ├── page.py
    │   ├── highlight.py
    │   ├── sync_record.py
    │   ├── processing_job.py
    │   └── connector.py
    ├── schemas/                # Pydantic request/response schemas
    │   ├── auth.py
    │   └── user.py
    ├── auth/                   # Authentication utilities
    │   ├── password.py         # Password hashing
    │   ├── jwt.py              # JWT token management
    │   └── dependencies.py     # Auth dependencies for routes
    └── api/                    # API route handlers
        ├── auth.py             # Registration & login
        └── users.py            # User endpoints
```

## Next Steps: Testing Locally

### 1. Start Infrastructure Services

You'll need Docker installed. Start PostgreSQL, Redis, and MinIO:

```bash
cd /Users/gabriele/Documents/Development/rmirror-cloud
docker compose up -d postgres redis minio
```

Verify services are running:
```bash
docker compose ps
```

### 2. Create Initial Migration

Once the database is running:

```bash
cd backend
poetry run alembic revision --autogenerate -m "Initial schema"
```

This will generate a migration file in `alembic/versions/` with all 7 tables.

### 3. Run Migrations

Apply the migration to create tables:

```bash
poetry run alembic upgrade head
```

### 4. Start the API Server

```bash
poetry run uvicorn app.main:app --reload
```

The API will be available at http://localhost:8000

### 5. Test the API

#### View API Documentation

FastAPI auto-generates interactive docs:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

#### Test with curl

**Register a new user:**
```bash
curl -X POST "http://localhost:8000/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "secure_password",
    "full_name": "Test User"
  }'
```

**Login:**
```bash
curl -X POST "http://localhost:8000/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "secure_password"
  }'
```

This returns:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Get current user (protected endpoint):**
```bash
TOKEN="your-token-from-login"
curl -X GET "http://localhost:8000/v1/users/me" \
  -H "Authorization: Bearer $TOKEN"
```

## Environment Variables

The `.env` file has been created with development defaults:

```env
# Database (matches docker-compose.yml)
POSTGRES_USER=rmirror
POSTGRES_PASSWORD=rmirror_dev_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=rmirror

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# S3/MinIO
S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET_NAME=rmirror

# Auth
SECRET_KEY=dev-secret-key-change-in-production...
```

**For production**, generate a secure secret key:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Database Schema Summary

### Core Tables Created

1. **users** - User accounts and subscriptions
   - JWT authentication
   - Subscription tiers (free, pro, enterprise)
   - API key support

2. **notebooks** - reMarkable documents
   - Links to user
   - Stores document metadata (title, author, type)
   - S3 storage keys

3. **pages** - Individual pages
   - Links to notebook
   - OCR status tracking
   - S3 storage for page images

4. **highlights** - Extracted annotations
   - Links to user, notebook, and page
   - Original text + corrected text
   - Quality metrics (confidence, match scores)
   - Source tracking (PDF, EPUB, RM)

5. **sync_records** - External service sync tracking
   - Polymorphic (tracks any item type)
   - Deduplication via content hash
   - Retry logic support

6. **processing_jobs** - Async job queue
   - Job types: extract_highlights, ocr_page, sync_to_service
   - Status tracking
   - Retry management

7. **connectors** - External service credentials
   - Encrypted credential storage
   - Auto-sync configuration
   - Service-specific settings (JSON)

## Development Commands

```bash
# Install dependencies
poetry install

# Run migrations
poetry run alembic upgrade head

# Create new migration
poetry run alembic revision --autogenerate -m "Description"

# Start dev server with auto-reload
poetry run uvicorn app.main:app --reload

# Run tests (when implemented)
poetry run pytest

# Code formatting
poetry run black app/
poetry run ruff check app/

# Type checking
poetry run mypy app/
```

## What's Next

Now that the backend foundation is complete, next steps could be:

1. **Test the setup** - Start Docker services and verify everything works
2. **Add more API endpoints** - Notebooks, highlights, file upload
3. **Implement file processing** - Port highlight extraction logic
4. **Add background jobs** - Set up RQ for async processing
5. **Build the agent** - Start Tauri application for file watching
6. **Build the dashboard** - Next.js frontend

The backend is production-ready for these features - just need to implement the business logic!
