"""
Flask web UI for rMirror Agent configuration and monitoring.
"""

from flask import Flask, render_template, jsonify, request

from app.config import Config
from app.sync.cloud_sync import CloudSync


def create_app(config: Config, cloud_sync: CloudSync) -> Flask:
    """
    Create and configure the Flask web application.

    Args:
        config: Agent configuration
        cloud_sync: Cloud sync client

    Returns:
        Configured Flask app
    """
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "rmirror-agent-secret"  # TODO: Make this configurable

    # Store references
    app.config["AGENT_CONFIG"] = config
    app.config["CLOUD_SYNC"] = cloud_sync

    # Register routes
    from app.web.routes import register_routes
    register_routes(app)

    return app
