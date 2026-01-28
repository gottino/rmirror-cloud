"""
Flask web UI for rMirror Agent configuration and monitoring.
"""

import os
import secrets
from typing import TYPE_CHECKING

from flask import Flask

from app.config import Config
from app.sync.cloud_sync import CloudSync

if TYPE_CHECKING:
    from app.main import Agent

# Cache the secret key for the session
_flask_secret_key: str | None = None


def _get_flask_secret_key() -> str:
    """Get or generate a Flask secret key.

    Uses environment variable if set, otherwise generates a secure random key.
    The key persists for the app's lifetime but is regenerated on restart.
    """
    global _flask_secret_key

    if _flask_secret_key is not None:
        return _flask_secret_key

    # Check for environment variable first (useful for testing)
    env_key = os.environ.get("RMIRROR_FLASK_SECRET_KEY")
    if env_key:
        _flask_secret_key = env_key
    else:
        # Generate a secure random key (64 hex chars = 32 bytes)
        _flask_secret_key = secrets.token_hex(32)

    return _flask_secret_key


def create_app(config: Config, cloud_sync: CloudSync, agent: "Agent" = None) -> Flask:
    """
    Create and configure the Flask web application.

    Args:
        config: Agent configuration
        cloud_sync: Cloud sync client
        agent: Reference to the main Agent instance (optional)

    Returns:
        Configured Flask app
    """
    app = Flask(__name__)
    app.config["SECRET_KEY"] = _get_flask_secret_key()

    # Store references
    app.config["AGENT_CONFIG"] = config
    app.config["CLOUD_SYNC"] = cloud_sync
    app.config["AGENT"] = agent

    # Register routes
    from app.web.routes import register_routes
    register_routes(app)

    return app
