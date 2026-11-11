"""
Flask web UI for rMirror Agent configuration and monitoring.
"""

import os
import secrets
from typing import TYPE_CHECKING

from flask import Flask, request

from app.agent_loop import AgentLoop
from app.config import Config
from app.logging_config import install_werkzeug_redaction
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


def _allowed_hosts(port: int) -> set[str]:
    """Host header values the local web UI answers to."""
    hosts = {f"localhost:{port}", f"127.0.0.1:{port}"}
    if port == 80:
        hosts |= {"localhost", "127.0.0.1"}
    return hosts


def create_app(
    config: Config,
    cloud_sync: CloudSync,
    agent: "Agent" = None,
    agent_loop: AgentLoop | None = None,
) -> Flask:
    """
    Create and configure the Flask web application.

    Args:
        config: Agent configuration
        cloud_sync: Cloud sync client
        agent: Reference to the main Agent instance (optional)
        agent_loop: The agent's event loop; routes run their coroutines on it

    Returns:
        Configured Flask app
    """
    app = Flask(__name__)
    app.config["SECRET_KEY"] = _get_flask_secret_key()

    # Store references
    app.config["AGENT_CONFIG"] = config
    app.config["CLOUD_SYNC"] = cloud_sync
    app.config["AGENT"] = agent
    app.config["AGENT_LOOP"] = agent_loop

    # Only serve requests addressed to this agent on the loopback names, and
    # refuse state-changing requests that come from another site.
    allowed_hosts = _allowed_hosts(config.web.port)
    allowed_origins = {f"http://{host}" for host in allowed_hosts}

    @app.before_request
    def _reject_foreign_requests():
        host = (request.headers.get("Host") or "").lower()
        if host not in allowed_hosts:
            return "Forbidden", 403

        if request.method in ("GET", "HEAD", "OPTIONS"):
            # Top-level navigations (e.g. /auth/callback coming back from the
            # dashboard) are cross-site by nature; /auth/callback is protected
            # by its one-time state instead.
            return None

        origin = request.headers.get("Origin")
        if origin is not None and origin.lower() not in allowed_origins:
            return "Forbidden", 403
        if request.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
            return "Forbidden", 403
        return None

    install_werkzeug_redaction()

    # Register routes
    from app.web.routes import register_routes
    register_routes(app)

    return app
