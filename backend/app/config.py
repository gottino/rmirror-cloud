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

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug(cls, v):
        """Handle empty string for debug field (defaults to False)."""
        if v == "" or v is None:
            return False
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)

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

    # S3/MinIO Storage. Outside debug, local storage needs STORAGE_BACKEND=local.
    storage_backend: Optional[str] = None  # "s3" or "local"; unset = S3 if configured
    s3_endpoint_url: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None
    s3_bucket_name: str = "rmirror"
    s3_region: str = "us-east-1"
    s3_key_prefix: str = ""  # Set to "staging/" for staging environment

    # Google AI API for OCR (Gemini)
    google_ai_api_key: Optional[str] = None
    ocr_model: str = "gemini-2.5-flash"

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
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5555",
        "http://127.0.0.1:5555",
    ]

    # File Processing
    max_upload_size: int = 100 * 1024 * 1024  # 100MB, documents (PDF/EPUB)
    max_rm_file_size: int = 10 * 1024 * 1024  # 10MB, a single .rm page file
    max_metadata_file_size: int = 1024 * 1024  # 1MB, .metadata and .content JSON
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

    # Todoist OAuth Integration
    todoist_client_id: Optional[str] = None
    todoist_client_secret: Optional[str] = None
    todoist_redirect_uri: Optional[str] = None

    # Integration Encryption
    integration_master_key: Optional[str] = None

    # Umami Analytics (optional - backend event tracking)
    umami_url: Optional[str] = None
    umami_website_id: Optional[str] = None

    # Agent Downloads
    agent_latest_version: str = "1.6.0"
    agent_download_url_macos: str = ""

    # Beta / Admin
    admin_user_ids: str = ""  # comma-separated Clerk user IDs
    invite_token_expiry_days: int = 7
    dashboard_url: str = "https://rmirror.io"
    beta_signup_enabled: bool = True  # Set to False when beta period ends


# Settings that must be set outside debug mode (environment variable names).
# This is the single list used by the start-up check and scripts/check_config.py.
REQUIRED_OUTSIDE_DEBUG = [
    "SECRET_KEY",
    "CLERK_JWKS_URL",
    "CLERK_SECRET_KEY",
    "CLERK_WEBHOOK_SECRET",
    "GOOGLE_AI_API_KEY",
    "INTEGRATION_MASTER_KEY",
]

# Required unless STORAGE_BACKEND=local.
REQUIRED_FOR_S3 = [
    "S3_ENDPOINT_URL",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "S3_BUCKET_NAME",
]

# Integrations without an on/off switch: switched on by setting any of their
# values, after which all of them are required.
INTEGRATION_GROUPS = {
    "Notion": ["NOTION_CLIENT_ID", "NOTION_CLIENT_SECRET", "NOTION_REDIRECT_URI"],
    "Todoist": ["TODOIST_CLIENT_ID", "TODOIST_CLIENT_SECRET", "TODOIST_REDIRECT_URI"],
}


def _is_unset(settings, name: str) -> bool:
    value = getattr(settings, name.lower(), None)
    return value is None or not str(value).strip()


def config_problems(settings) -> tuple[list[str], list[str]]:
    """Return (missing, warnings) for the settings a non-debug run needs.

    Only setting NAMES are returned, never values. `missing` makes start-up
    fail outside debug; `warnings` are optional features that are not set up.
    """
    missing = [n for n in REQUIRED_OUTSIDE_DEBUG if _is_unset(settings, n)]

    backend = (settings.storage_backend or "").strip().lower()
    if backend not in ("", "s3", "local"):
        missing.append("STORAGE_BACKEND (must be 's3' or 'local')")
    elif backend != "local":
        missing.extend(n for n in REQUIRED_FOR_S3 if _is_unset(settings, n))

    warnings = []
    if _is_unset(settings, "RESEND_API_KEY"):
        warnings.append("RESEND_API_KEY (email is disabled)")
    for label, names in INTEGRATION_GROUPS.items():
        unset = [n for n in names if _is_unset(settings, n)]
        if len(unset) == len(names):
            warnings.append(f"{label} integration is not configured")
        else:
            missing.extend(unset)
    return missing, warnings


def validate_startup(settings, logger) -> None:
    """Fail start-up outside debug when required settings are missing."""
    missing, warnings = config_problems(settings)
    if warnings:
        logger.warning("Optional features not configured: %s", "; ".join(warnings))
    if not missing:
        return
    names = ", ".join(missing)
    if settings.debug:
        logger.warning("Debug mode: continuing with missing settings: %s", names)
        return
    raise RuntimeError(
        f"Missing or invalid settings: {names}. Set them in the environment or "
        ".env (see .env.example), or set DEBUG=true for local development."
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
