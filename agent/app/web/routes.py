"""
Flask routes for rMirror Agent web UI.
"""

from pathlib import Path

from flask import Flask, jsonify, render_template, request

from app.config import Config
from app.sync.cloud_sync import CloudSync, CloudSyncError


def register_routes(app: Flask) -> None:
    """Register all web UI routes."""

    @app.route("/")
    def index():
        """Main dashboard page."""
        config: Config = app.config["AGENT_CONFIG"]
        return render_template(
            "index.html",
            config=config,
            api_url=config.api.url,
            email=config.api.email,
            remarkable_dir=config.remarkable.source_directory,
            auto_sync=config.sync.auto_sync,
        )

    @app.route("/api/status")
    def api_status():
        """Get agent status."""
        config: Config = app.config["AGENT_CONFIG"]
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]

        return jsonify(
            {
                "agent": {
                    "running": True,
                    "version": "0.1.0",
                },
                "authentication": {
                    "authenticated": cloud_sync.authenticated,
                    "email": config.api.email,
                },
                "watching": {
                    "enabled": config.remarkable.watch_enabled,
                    "directory": config.remarkable.source_directory,
                    "exists": Path(config.remarkable.source_directory).exists(),
                },
                "sync": {
                    "auto_sync": config.sync.auto_sync,
                    "batch_size": config.sync.batch_size,
                    "sync_interval": config.sync.sync_interval,
                },
            }
        )

    @app.route("/api/config", methods=["GET", "POST"])
    def api_config():
        """Get or update configuration."""
        config: Config = app.config["AGENT_CONFIG"]

        if request.method == "GET":
            return jsonify(
                {
                    "api": {
                        "url": config.api.url,
                        "email": config.api.email,
                    },
                    "remarkable": {
                        "source_directory": config.remarkable.source_directory,
                        "watch_enabled": config.remarkable.watch_enabled,
                    },
                    "sync": {
                        "auto_sync": config.sync.auto_sync,
                        "batch_size": config.sync.batch_size,
                        "sync_interval": config.sync.sync_interval,
                    },
                }
            )

        # POST - Update configuration
        data = request.json

        # Update API config
        if "api" in data:
            if "url" in data["api"]:
                config.api.url = data["api"]["url"]
            if "email" in data["api"]:
                config.api.email = data["api"]["email"]
            if "password" in data["api"]:
                config.api.password = data["api"]["password"]

        # Update reMarkable config
        if "remarkable" in data:
            if "source_directory" in data["remarkable"]:
                config.remarkable.source_directory = data["remarkable"]["source_directory"]
            if "watch_enabled" in data["remarkable"]:
                config.remarkable.watch_enabled = data["remarkable"]["watch_enabled"]

        # Update sync config
        if "sync" in data:
            if "auto_sync" in data["sync"]:
                config.sync.auto_sync = data["sync"]["auto_sync"]
            if "batch_size" in data["sync"]:
                config.sync.batch_size = data["sync"]["batch_size"]
            if "sync_interval" in data["sync"]:
                config.sync.sync_interval = data["sync"]["sync_interval"]

        # Save configuration
        config.save()

        return jsonify({"success": True, "message": "Configuration updated"})

    @app.route("/api/sync/status")
    def api_sync_status():
        """Get sync status from backend."""
        import asyncio
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]

        try:
            # Run async function in sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                status = loop.run_until_complete(cloud_sync.get_sync_status())
                return jsonify(status)
            finally:
                loop.close()
        except CloudSyncError as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/sync/trigger", methods=["POST"])
    def api_sync_trigger():
        """Trigger immediate sync."""
        # TODO: Implement manual sync trigger
        return jsonify({"success": True, "message": "Manual sync triggered"})

    @app.route("/api/test-connection", methods=["POST"])
    def api_test_connection():
        """Test connection to backend API."""
        import asyncio
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]

        try:
            # Run async function in sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(cloud_sync.authenticate())
                return jsonify(
                    {
                        "success": True,
                        "message": f"Successfully authenticated as {cloud_sync.config.api.email}",
                    }
                )
            finally:
                loop.close()
        except CloudSyncError as e:
            return jsonify({"success": False, "message": str(e)}), 401

    @app.route("/auth/callback")
    def auth_callback():
        """
        Handle Clerk OAuth callback redirect with JWT token in URL.

        Expected query parameter:
        ?token=clerk_jwt_token
        """
        config: Config = app.config["AGENT_CONFIG"]

        try:
            token = request.args.get("token")
            if not token:
                return render_template("auth_result.html", success=False, message="Missing authentication token")

            # Store the JWT token in config
            config.api.token = token
            config.api.use_clerk_auth = True

            # Save configuration
            config.save()

            # Mark cloud sync as authenticated
            cloud_sync: CloudSync = app.config["CLOUD_SYNC"]
            cloud_sync.authenticated = True

            return render_template("auth_result.html", success=True, message="Successfully authenticated with Clerk!")
        except Exception as e:
            return render_template("auth_result.html", success=False, message=str(e))

    @app.route("/api/auth/status")
    def api_auth_status():
        """Get current authentication status."""
        config: Config = app.config["AGENT_CONFIG"]
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]

        return jsonify({
            "authenticated": cloud_sync.authenticated,
            "use_clerk_auth": config.api.use_clerk_auth,
            "has_token": bool(config.api.token),
            "clerk_frontend_api": config.api.clerk_frontend_api,
        })

    @app.route("/health")
    def health():
        """Health check endpoint."""
        return jsonify({"status": "healthy"})
