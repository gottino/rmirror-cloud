"""Application configuration and settings."""

import logging
from functools import lru_cache
from typing import Optional
from urllib.parse import urlparse

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
    # Only non-security behaviour (log verbosity). Security checks have their
    # own flags below, which the app refuses to enable outside SQLite.
    debug: bool = False
    api_version: str = "v1"

    # Insecure development flags (default off). Each one relaxes one security
    # check; see check_insecure_flags() for the start-up guard.
    # Accept Clerk session tokens without a signature check when
    # CLERK_JWKS_URL is not set (local development without Clerk).
    allow_unverified_clerk_tokens: bool = False
    # Accept Clerk webhooks without a signature when CLERK_WEBHOOK_SECRET is unset.
    allow_unsigned_webhooks: bool = False
    # Skip TLS certificate verification on Notion OAuth/API calls.
    disable_tls_verify: bool = False

    @field_validator(
        "debug",
        "allow_unverified_clerk_tokens",
        "allow_unsigned_webhooks",
        "disable_tls_verify",
        mode="before",
    )
    @classmethod
    def parse_debug(cls, v):
        """Handle empty string for boolean flags (defaults to False)."""
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

    # S3/MinIO Storage (optional - uses local storage if not configured)
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
    # Expected ``iss`` claim of Clerk session tokens. When unset it is derived
    # from CLERK_JWKS_URL by stripping "/.well-known/jwks.json".
    clerk_issuer: Optional[str] = None
    # Accepted ``azp`` (authorised party) values of Clerk session tokens, as a
    # JSON list like CORS_ORIGINS, e.g. ["https://rmirror.io"]. Opt-in: when
    # unset (the default) ``azp`` is not enforced; a token whose ``azp`` is not
    # in ``default_authorized_parties()`` only logs a warning. When set to a
    # non-empty list, tokens with any other ``azp`` are rejected. Tokens without
    # an ``azp`` claim are always accepted.
    clerk_authorized_parties: Optional[list[str]] = None

    # CORS
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5555",
        "http://127.0.0.1:5555",
    ]

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

    # Rate limiting (slowapi / limits). See app/middleware/rate_limit.py.
    # memory:// keeps counters per uvicorn worker process, so with N workers a
    # client can make up to N times each limit. Point this at a shared limits
    # storage (e.g. redis://...) to make the limits exact across workers.
    rate_limit_storage_uri: str = "memory://"
    # Applied to every route without its own limit (keyed per client IP, since
    # it is checked before authentication runs).
    rate_limit_default: str = "300/minute"
    # Stricter limits for routes reachable without a dashboard session.
    rate_limit_unauthenticated: str = "10/minute"  # waitlist sign-up / invite check
    rate_limit_webhook: str = "60/minute"  # Clerk webhook (senders retry on 429)
    rate_limit_obsidian_sync: str = "60/minute"  # Obsidian pull, per user
    # .rm uploads, per user. An initial sync uploads every page of every
    # notebook back to back; 120/minute (2 pages a second) lets the agent
    # work through a large library without stalling while still capping abuse.
    rate_limit_upload: str = "120/minute"

    # Sync queue retention. The sync worker deletes finished sync_queue rows
    # older than these many days, in small batches, about once an hour.
    # Pending and processing rows, sync_records, pages and notebooks are never
    # pruned. 0 or less disables pruning for that status.
    sync_queue_completed_retention_days: int = 30
    sync_queue_failed_retention_days: int = 90

    def default_authorized_parties(self) -> list[str]:
        """Origins expected as ``azp``: CORS origins plus the DASHBOARD_URL origin.

        Used only to decide which unlisted ``azp`` values are worth a warning
        while CLERK_AUTHORIZED_PARTIES is unset; it is never enforced.
        """
        parties = [o.rstrip("/") for o in self.cors_origins]
        parsed = urlparse(self.dashboard_url)
        if parsed.scheme and parsed.netloc:
            parties.append(f"{parsed.scheme}://{parsed.netloc}")
        return list(dict.fromkeys(parties))

    def enabled_insecure_flags(self) -> list[str]:
        """Names (as environment variables) of the insecure flags that are on."""
        flags = {
            "ALLOW_UNVERIFIED_CLERK_TOKENS": self.allow_unverified_clerk_tokens,
            "ALLOW_UNSIGNED_WEBHOOKS": self.allow_unsigned_webhooks,
            "DISABLE_TLS_VERIFY": self.disable_tls_verify,
        }
        return [name for name, enabled in flags.items() if enabled]


def check_insecure_flags(settings: "Settings") -> None:
    """Refuse insecure flags outside local SQLite development; warn when allowed.

    Called once at start-up (app/main.py).

    Raises:
        RuntimeError: if any insecure flag is on while DATABASE_URL is not SQLite.
    """
    enabled = settings.enabled_insecure_flags()
    if not enabled:
        return
    names = ", ".join(enabled)
    if not settings.database_url.startswith("sqlite"):
        raise RuntimeError(
            f"Refusing to start: insecure setting(s) {names} enabled while "
            "DATABASE_URL is not SQLite. These flags are for local development "
            "only; unset them (or set them to false)."
        )
    logging.getLogger(__name__).warning(
        "!!! INSECURE DEVELOPMENT SETTINGS ENABLED: %s. "
        "Never use these outside local development. !!!",
        names,
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
