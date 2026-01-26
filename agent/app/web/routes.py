"""
Flask routes for rMirror Agent web UI.
"""

import asyncio
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from app.config import Config
from app.sync.cloud_sync import CloudSync, CloudSyncError

# Lock to prevent concurrent async operations from interfering with each other
# This is necessary because Flask uses multiple threads but httpx clients are
# bound to the event loop they were created in
_async_lock = threading.Lock()


@contextmanager
def run_async_safely(cloud_sync: CloudSync) -> Generator[asyncio.AbstractEventLoop, None, None]:
    """
    Context manager to safely run async code in Flask.

    Uses a lock to ensure only one async operation runs at a time, preventing
    concurrent requests from interfering with each other's httpx clients.
    """
    with _async_lock:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            yield loop
        finally:
            # Invalidate the client reference so it gets recreated on next request
            if cloud_sync:
                cloud_sync.client = None
            loop.close()


async def register_agent_with_backend(
    cloud_sync: CloudSync,
    version: str,
    platform: str,
    hostname: str
) -> None:
    """
    Register agent with backend after successful authentication.

    Args:
        cloud_sync: CloudSync instance
        version: Agent version
        platform: Platform (e.g., "Darwin" for macOS)
        hostname: Machine hostname
    """
    # Initialize HTTP client if not exists
    if not cloud_sync.client:
        import httpx
        cloud_sync.client = httpx.AsyncClient(timeout=30.0)

    try:
        response = await cloud_sync.client.post(
            f"{cloud_sync.config.api.url}/agents/register",
            headers={"Authorization": f"Bearer {cloud_sync.config.api.token}"},
            json={
                "version": version,
                "platform": platform,
                "hostname": hostname,
            },
        )
        response.raise_for_status()
        print("✓ Agent registered with backend")
    except Exception as e:
        print(f"⚠ Failed to register agent with backend: {e}")
        raise


def register_routes(app: Flask) -> None:
    """Register all web UI routes."""

    @app.route("/")
    def index():
        """Main dashboard page."""
        config: Config = app.config["AGENT_CONFIG"]
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]
        return render_template(
            "index.html",
            config=config,
            api_url=config.api.url,
            email=config.api.email,
            remarkable_dir=config.remarkable.source_directory,
            auto_sync=config.sync.auto_sync,
            max_pages_per_notebook=config.sync.max_pages_per_notebook,
            use_clerk_auth=config.api.use_clerk_auth,
            authenticated=cloud_sync.authenticated if cloud_sync else False,
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
                    "authenticated": cloud_sync.authenticated if cloud_sync else False,
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
            if "max_pages_per_notebook" in data["sync"]:
                config.sync.max_pages_per_notebook = data["sync"]["max_pages_per_notebook"]

        # Save configuration
        config.save()

        return jsonify({"success": True, "message": "Configuration updated"})

    @app.route("/api/sync/status")
    def api_sync_status():
        """Get sync status from backend."""
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]

        try:
            with run_async_safely(cloud_sync) as loop:
                status = loop.run_until_complete(cloud_sync.get_sync_status())
                return jsonify(status)
        except CloudSyncError as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/sync/trigger", methods=["POST"])
    def api_sync_trigger():
        """Trigger immediate sync."""
        # TODO: Implement manual sync trigger
        return jsonify({"success": True, "message": "Manual sync triggered"})

    @app.route("/api/sync/initial", methods=["POST"])
    def api_sync_initial():
        """
        Trigger initial sync of all notebooks.

        This uploads all pages and .content files for selected notebooks.
        Useful for first-time setup or catching up after being offline.
        """
        from app.sync.initial_sync import InitialSync

        config: Config = app.config["AGENT_CONFIG"]
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]

        if not cloud_sync or not cloud_sync.authenticated:
            return jsonify({"success": False, "message": "Not authenticated"}), 401

        try:
            # Get selected notebooks
            selected_uuids = None
            if not config.sync.sync_all_notebooks:
                selected_uuids = config.sync.selected_notebooks

            # Run initial sync
            initial_sync = InitialSync(config, cloud_sync)

            with run_async_safely(cloud_sync) as loop:
                stats = loop.run_until_complete(initial_sync.run(selected_uuids))
                return jsonify({
                    "success": True,
                    "message": "Initial sync complete",
                    "stats": stats,
                })

        except Exception as e:
            app.logger.error(f"Initial sync failed: {e}", exc_info=True)
            return jsonify({"success": False, "message": str(e)}), 500

    @app.route("/api/test-connection", methods=["POST"])
    def api_test_connection():
        """Test connection to backend API."""
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]

        try:
            with run_async_safely(cloud_sync) as loop:
                loop.run_until_complete(cloud_sync.authenticate())
                return jsonify(
                    {
                        "success": True,
                        "message": f"Successfully authenticated as {cloud_sync.config.api.email}",
                    }
                )
        except CloudSyncError as e:
            return jsonify({"success": False, "message": str(e)}), 401

    @app.route("/auth/callback")
    def auth_callback():
        """
        Handle Clerk OAuth callback redirect with JWT token in URL.

        Expected query parameter:
        ?token=clerk_jwt_token
        """
        import platform

        config: Config = app.config["AGENT_CONFIG"]

        try:
            token = request.args.get("token")
            if not token:
                return render_template("auth_result.html", success=False, message="Missing authentication token")

            # Store the JWT token in config (will be saved to keychain)
            config.api.token = token
            config.api.use_clerk_auth = True

            # Save configuration
            config.save()

            # Mark cloud sync as authenticated
            cloud_sync: CloudSync = app.config["CLOUD_SYNC"]
            cloud_sync.authenticated = True

            # Register agent with backend
            try:
                with run_async_safely(cloud_sync) as loop:
                    # Get agent info
                    agent_version = "1.0.0"
                    agent_platform = platform.system()
                    agent_hostname = platform.node()

                    # Register with backend
                    loop.run_until_complete(register_agent_with_backend(
                        cloud_sync,
                        agent_version,
                        agent_platform,
                        agent_hostname
                    ))
            except Exception as e:
                # Log error but don't fail authentication
                app.logger.error(f"Failed to register agent: {e}")

            # Start file watcher now that we're authenticated
            agent = app.config.get("AGENT")
            if agent and config.remarkable.watch_enabled:
                try:
                    agent.start_file_watcher_sync()
                    app.logger.info("File watcher started after authentication")
                except Exception as e:
                    app.logger.error(f"Failed to start file watcher: {e}")

            return render_template("auth_result.html", success=True, message="Successfully authenticated with Clerk!")
        except Exception as e:
            return render_template("auth_result.html", success=False, message=str(e))

    @app.route("/api/auth/status")
    def api_auth_status():
        """Get current authentication status."""
        config: Config = app.config["AGENT_CONFIG"]
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]

        return jsonify({
            "authenticated": cloud_sync.authenticated if cloud_sync else False,
            "use_clerk_auth": config.api.use_clerk_auth,
            "has_token": bool(config.api.token),
            "clerk_frontend_api": config.api.clerk_frontend_api,
            "email": cloud_sync.user_email if cloud_sync else None,
        })

    @app.route("/api/auth/me")
    def api_auth_me():
        """Get current user info from backend."""
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]

        if not cloud_sync or not cloud_sync.authenticated:
            return jsonify({"error": "Not authenticated"}), 401

        try:
            with run_async_safely(cloud_sync) as loop:
                user_data = loop.run_until_complete(cloud_sync.get_user_info())
                return jsonify(user_data)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/auth/logout", methods=["POST"])
    def api_auth_logout():
        """Sign out and clear stored token."""
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]

        if cloud_sync:
            cloud_sync.logout()

        return jsonify({"success": True, "message": "Signed out successfully"})

    @app.route("/api/notebooks/tree")
    def api_notebooks_tree():
        """Get folder tree structure from reMarkable metadata."""
        from app.remarkable.metadata_scanner import MetadataScanner

        config: Config = app.config["AGENT_CONFIG"]

        try:
            scanner = MetadataScanner(Path(config.remarkable.source_directory))
            tree_items = scanner.scan()
            tree = scanner.to_dict(tree_items)

            # Get statistics
            total_documents = len(scanner.get_all_document_uuids())
            total_pages = scanner.count_total_pages()
            selected_pages = scanner.count_total_pages(config.sync.selected_notebooks) if not config.sync.sync_all_notebooks else total_pages

            return jsonify({
                "tree": tree,
                "stats": {
                    "total_documents": total_documents,
                    "total_pages": total_pages,
                    "selected_pages": selected_pages,
                },
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/notebooks/selection", methods=["GET", "POST"])
    def api_notebooks_selection():
        """Get or update notebook selection."""
        config: Config = app.config["AGENT_CONFIG"]

        if request.method == "GET":
            return jsonify({
                "sync_all_notebooks": config.sync.sync_all_notebooks,
                "selected_notebooks": config.sync.selected_notebooks,
            })

        # POST - Update selection
        data = request.json

        if "sync_all_notebooks" in data:
            config.sync.sync_all_notebooks = data["sync_all_notebooks"]

        if "selected_notebooks" in data:
            config.sync.selected_notebooks = data["selected_notebooks"]

        # Save configuration
        config.save()

        return jsonify({"success": True, "message": "Notebook selection updated"})

    @app.route("/api/quota")
    def api_quota():
        """Get quota status from backend."""
        cloud_sync: CloudSync = app.config["CLOUD_SYNC"]

        if not cloud_sync or not cloud_sync.authenticated:
            return jsonify({"error": "Not authenticated"}), 401

        try:
            with run_async_safely(cloud_sync) as loop:
                quota_data = loop.run_until_complete(cloud_sync.get_quota_status())
                return jsonify(quota_data)
        except Exception as e:
            print(f"Quota status request error: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/health")
    def health():
        """Health check endpoint."""
        return jsonify({"status": "healthy"})
