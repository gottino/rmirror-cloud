"""Configuration management for rMirror Agent."""

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.auth.keychain import get_keychain_manager


class APIConfig(BaseSettings):
    """API configuration."""

    url: str = Field(default="https://rmirror.io/api/v1", description="rMirror Cloud API URL")
    email: str = Field(default="", description="User email (for legacy password auth)")
    password: str = Field(default="", description="User password (for legacy password auth)")
    _token: Optional[str] = None  # Private field, use token property instead

    # Clerk OAuth configuration
    clerk_frontend_api: str = Field(
        default="https://rmirror.io",
        description="Clerk frontend API URL for OAuth"
    )
    use_clerk_auth: bool = Field(
        default=True,
        description="Use Clerk OAuth instead of email/password"
    )

    model_config = SettingsConfigDict(env_prefix="RMIRROR_API_", extra="ignore")

    @property
    def token(self) -> Optional[str]:
        """Get token from keychain if available, otherwise return in-memory token."""
        if self._token:
            return self._token

        # Try to get from keychain
        keychain = get_keychain_manager()
        return keychain.get_token()

    @token.setter
    def token(self, value: Optional[str]) -> None:
        """Set token and store in keychain for persistence."""
        self._token = value
        if value:
            # Store in keychain for persistence
            keychain = get_keychain_manager()
            keychain.store_token(value)

    def clear_token(self) -> None:
        """Clear token from both memory and keychain."""
        self._token = None
        keychain = get_keychain_manager()
        keychain.delete_token()


class ReMarkableConfig(BaseSettings):
    """reMarkable Desktop app configuration."""

    source_directory: str = Field(
        default=str(
            Path.home()
            / "Library/Containers/com.remarkable.desktop/Data/Library/Application Support/remarkable/desktop"
        ),
        description="reMarkable Desktop sync folder",
    )
    watch_enabled: bool = Field(default=True, description="Enable file watching")

    model_config = SettingsConfigDict(env_prefix="RMIRROR_REMARKABLE_", extra="ignore")

    @field_validator("source_directory")
    @classmethod
    def expand_path(cls, v: str) -> str:
        """Expand ~ and environment variables in path."""
        return str(Path(v).expanduser().resolve())


class WebConfig(BaseSettings):
    """Web UI configuration."""

    enabled: bool = Field(default=True, description="Enable web UI")
    port: int = Field(default=5555, description="Web UI port")
    host: str = Field(default="127.0.0.1", description="Web UI host")
    auto_launch_browser: bool = Field(default=True, description="Auto-launch browser on startup")
    app_mode: bool = Field(default=True, description="Launch browser in app mode (no browser chrome)")

    model_config = SettingsConfigDict(env_prefix="RMIRROR_WEB_", extra="ignore")


class TrayConfig(BaseSettings):
    """System tray configuration."""

    enabled: bool = Field(default=True, description="Enable system tray icon")
    show_notifications: bool = Field(default=True, description="Show desktop notifications")

    model_config = SettingsConfigDict(env_prefix="RMIRROR_TRAY_", extra="ignore")


class SyncConfig(BaseSettings):
    """Sync configuration."""

    auto_sync: bool = Field(default=True, description="Enable automatic syncing")
    batch_size: int = Field(default=10, description="Number of files to upload in one batch")
    retry_attempts: int = Field(default=3, description="Number of retry attempts for failed uploads")
    sync_interval: int = Field(default=60, description="Sync interval in seconds")
    cooldown_seconds: int = Field(
        default=5, description="Cooldown period to deduplicate file events"
    )
    selected_notebooks: list[str] = Field(
        default_factory=list,
        description="List of notebook UUIDs to sync (empty = sync all)"
    )
    sync_all_notebooks: bool = Field(
        default=True,
        description="Sync all notebooks (ignores selected_notebooks if True)"
    )

    model_config = SettingsConfigDict(env_prefix="RMIRROR_SYNC_", extra="ignore")


class Config(BaseSettings):
    """Main configuration."""

    api: APIConfig = Field(default_factory=APIConfig)
    remarkable: ReMarkableConfig = Field(default_factory=ReMarkableConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    tray: TrayConfig = Field(default_factory=TrayConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    @classmethod
    def from_yaml(cls, config_path: Path) -> "Config":
        """Load configuration from YAML file."""
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r") as f:
            data = yaml.safe_load(f)

        return cls(**data if data else {})

    @classmethod
    def get_default_config_path(cls) -> Path:
        """Get default configuration file path."""
        # Try these locations in order:
        config_locations = [
            Path.home() / ".config/rmirror/config.yaml",
            Path.home() / ".rmirror/config.yaml",
            Path.cwd() / "config.yaml",
        ]

        for path in config_locations:
            if path.exists():
                return path

        # Return default location (even if it doesn't exist)
        return Path.home() / ".config/rmirror/config.yaml"

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "Config":
        """
        Load configuration from file or environment variables.

        Priority (highest to lowest):
        1. Specified config_path
        2. RMIRROR_CONFIG_PATH environment variable
        3. Default config locations
        4. Environment variables
        5. Default values
        """
        # Check for config path in environment
        if config_path is None:
            env_config_path = os.getenv("RMIRROR_CONFIG_PATH")
            if env_config_path:
                config_path = Path(env_config_path)

        # Use default if no path specified
        if config_path is None:
            config_path = cls.get_default_config_path()

        # Load from YAML if file exists, otherwise use defaults + env vars
        if config_path.exists():
            print(f"Loading configuration from: {config_path}")
            return cls.from_yaml(config_path)
        else:
            print(f"Config file not found at {config_path}, using defaults and environment variables")
            return cls()

    def save(self, config_path: Optional[Path] = None) -> None:
        """Save configuration to YAML file."""
        if config_path is None:
            config_path = self.get_default_config_path()

        # Create parent directory if it doesn't exist
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to dict and save
        config_dict = {
            "api": self.api.model_dump(exclude={"token"}),  # Don't save token
            "remarkable": self.remarkable.model_dump(),
            "web": self.web.model_dump(),
            "tray": self.tray.model_dump(),
            "sync": self.sync.model_dump(),
        }

        with open(config_path, "w") as f:
            # Prevent YAML from wrapping long strings (like paths with spaces)
            yaml.safe_dump(
                config_dict,
                f,
                default_flow_style=False,
                sort_keys=False,
                width=float('inf'),  # Never wrap lines
            )

        print(f"Configuration saved to: {config_path}")
