"""
Flask web UI for rMirror Agent configuration and monitoring.
"""

from typing import TYPE_CHECKING

from flask import Flask

from app.config import Config
from app.sync.cloud_sync import CloudSync

if TYPE_CHECKING:
    from app.main import Agent


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
    app.config["SECRET_KEY"] = "rmirror-agent-secret"  # TODO: Make this configurable

    # Store references
    app.config["AGENT_CONFIG"] = config
    app.config["CLOUD_SYNC"] = cloud_sync
    app.config["AGENT"] = agent

    # Register routes
    from app.web.routes import register_routes
    register_routes(app)

    return app
