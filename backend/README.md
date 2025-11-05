# rMirror Cloud Backend

FastAPI backend for rMirror Cloud - cloud service for reMarkable tablet integration.

## Development

```bash
# Install dependencies
poetry install

# Run migrations
poetry run alembic upgrade head

# Start development server
poetry run uvicorn app.main:app --reload

# Run tests
poetry run pytest
```

## Environment Variables

Copy `.env.example` from the root directory and configure:

- `POSTGRES_*` - Database connection
- `REDIS_*` - Redis connection
- `S3_*` - Object storage (MinIO/S3)
- `SECRET_KEY` - JWT secret key

See `app/config.py` for full configuration options.
