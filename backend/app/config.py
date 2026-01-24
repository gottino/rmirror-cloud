"""Application configuration and settings."""

from functools import lru_cache
from typing import Optional

from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "rMirror Cloud API"
    debug: bool = False
    api_version: str = "v1"

    # Database
    database_url: str = "sqlite:///./rmirror.db"  # Default to SQLite for local dev
    postgres_user: Optional[str] = None
    postgres_password: Optional[str] = None
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "rmirror"

    @field_validator("database_url", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: Optional[str], info) -> str:
        """Build database URL from components if not provided."""
        if isinstance(v, str) and v:
            return v

        # Build PostgreSQL URL from components if postgres_user is provided
        data = info.data
        if data.get("postgres_user"):
            return str(
                PostgresDsn.build(
                    scheme="postgresql",
                    username=data.get("postgres_user"),
                    password=data.get("postgres_password"),
                    host=data.get("postgres_host", "localhost"),
                    port=data.get("postgres_port", 5432),
                    path=data.get("postgres_db", "rmirror"),
                )
            )

        # Default to SQLite
        return "sqlite:///./rmirror.db"

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_url: Optional[str] = None

    @field_validator("redis_url", mode="before")
    @classmethod
    def assemble_redis_connection(cls, v: Optional[str], info) -> str:
        """Build Redis URL from components if not provided."""
        if isinstance(v, str):
            return v

        data = info.data
        host = data.get("redis_host", "localhost")
        port = data.get("redis_port", 6379)
        db = data.get("redis_db", 0)
        return f"redis://{host}:{port}/{db}"

    # S3/MinIO Storage (optional - uses local storage if not configured)
    s3_endpoint_url: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None
    s3_bucket_name: str = "rmirror"
    s3_region: str = "us-east-1"
    s3_key_prefix: str = ""  # Set to "staging/" for staging environment

    # Claude API for OCR
    claude_api_key: Optional[str] = None

    # Authentication
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 7 days

    # Clerk Authentication (optional - for social login)
    clerk_publishable_key: Optional[str] = None
    clerk_secret_key: Optional[str] = None
    clerk_jwks_url: Optional[str] = None
    clerk_webhook_secret: Optional[str] = None

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # File Processing
    max_upload_size: int = 100 * 1024 * 1024  # 100MB
    allowed_file_types: list[str] = [".pdf", ".epub"]

    # Email Configuration (Resend)
    resend_api_key: Optional[str] = None
    resend_from_email: str = "noreply@rmirror.io"
    resend_from_name: str = "rMirror Cloud"
    admin_email: Optional[str] = None

    # Notion OAuth Integration
    notion_client_id: Optional[str] = None
    notion_client_secret: Optional[str] = None
    notion_redirect_uri: Optional[str] = None

    # Integration Encryption
    integration_master_key: Optional[str] = None


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
