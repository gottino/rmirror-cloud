"""Notion OAuth service for handling OAuth flow and database operations."""

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx
from notion_client import Client as NotionClient

from app.config import get_settings

logger = logging.getLogger(__name__)


class NotionOAuthService:
    """Service for handling Notion OAuth flow and database operations."""

    def __init__(self):
        """Initialize Notion OAuth service."""
        settings = get_settings()
        self.client_id = settings.notion_client_id
        self.client_secret = settings.notion_client_secret
        self.redirect_uri = settings.notion_redirect_uri
        self.debug = settings.debug
        self.logger = logger

        if not all([self.client_id, self.client_secret, self.redirect_uri]):
            logger.warning("Notion OAuth credentials not configured")

    def _get_http_client(self) -> httpx.Client:
        """
        Create httpx client with SSL verification based on debug mode.

        Returns:
            httpx.Client instance
        """
        return httpx.Client(verify=not self.debug)

    def _get_notion_client(self, access_token: str) -> NotionClient:
        """
        Create Notion client with SSL verification disabled in debug mode.

        Args:
            access_token: Notion OAuth access token

        Returns:
            NotionClient instance configured for API version 2025-09-03
        """
        if self.debug:
            # Create httpx client with SSL verification disabled
            http_client = self._get_http_client()
            return NotionClient(
                auth=access_token,
                client=http_client,
                notion_version="2025-09-03"  # Use new API version
            )
        else:
            return NotionClient(
                auth=access_token,
                notion_version="2025-09-03"  # Use new API version
            )

    def get_authorization_url(self, state: str) -> str:
        """
        Generate Notion OAuth authorization URL.

        Args:
            state: Random state string for CSRF protection

        Returns:
            Authorization URL for user to visit
        """
        logger.info(f"Building OAuth URL with client_id: {self.client_id}")
        logger.info(f"Redirect URI: {self.redirect_uri}")

        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "owner": "user",
            "redirect_uri": self.redirect_uri,
            "state": state,
        }

        base_url = "https://api.notion.com/v1/oauth/authorize"
        url = f"{base_url}?{urlencode(params)}"
        logger.info(f"Generated OAuth URL: {url}")
        return url

    async def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            Dict containing access_token, workspace_id, workspace_name, etc.

        Raises:
            httpx.HTTPError: If token exchange fails
        """
        settings = get_settings()

        # Disable SSL verification in development mode
        async with httpx.AsyncClient(verify=not settings.debug) as client:
            response = await client.post(
                "https://api.notion.com/v1/oauth/token",
                auth=(self.client_id, self.client_secret),
                json={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                },
                headers={"Content-Type": "application/json"},
            )

            response.raise_for_status()
            data = response.json()

            return {
                "access_token": data["access_token"],
                "workspace_id": data.get("workspace_id"),
                "workspace_name": data.get("workspace_name"),
                "workspace_icon": data.get("workspace_icon"),
                "bot_id": data.get("bot_id"),
                "owner": data.get("owner", {}),
            }

    async def list_databases(self, access_token: str) -> List[Dict[str, Any]]:
        """
        List all databases the integration has access to.

        Args:
            access_token: Notion OAuth access token

        Returns:
            List of database objects with id, title, and url
        """
        client = self._get_notion_client(access_token)

        try:
            # Search for all databases
            response = client.search(filter={"property": "object", "value": "database"})

            databases = []
            for db in response.get("results", []):
                title_parts = db.get("title", [])
                title = (
                    title_parts[0].get("plain_text", "Untitled")
                    if title_parts
                    else "Untitled"
                )

                databases.append({
                    "id": db["id"],
                    "title": title,
                    "url": db.get("url", ""),
                    "created_time": db.get("created_time", ""),
                    "last_edited_time": db.get("last_edited_time", ""),
                })

            return databases

        except Exception as e:
            logger.error(f"Error listing Notion databases: {e}")
            return []

    async def list_pages(self, access_token: str) -> List[Dict[str, Any]]:
        """
        List all pages the integration has access to (for parent selection).

        Args:
            access_token: Notion OAuth access token

        Returns:
            List of page objects with id, title, and url
        """
        client = self._get_notion_client(access_token)

        try:
            # Search for all pages
            response = client.search(filter={"property": "object", "value": "page"})

            pages = []
            for page in response.get("results", []):
                # Get title from properties
                title = "Untitled"
                properties = page.get("properties", {})
                for prop in properties.values():
                    if prop.get("type") == "title":
                        title_parts = prop.get("title", [])
                        if title_parts:
                            title = title_parts[0].get("plain_text", "Untitled")
                        break

                pages.append({
                    "id": page["id"],
                    "title": title,
                    "url": page.get("url", ""),
                    "created_time": page.get("created_time", ""),
                })

            return pages

        except Exception as e:
            logger.error(f"Error listing Notion pages: {e}")
            return []

    async def create_rmirror_database(
        self,
        access_token: str,
        parent_page_id: Optional[str] = None,
        database_title: str = "rMirror Notebooks",
        database_type: str = "notebooks",
    ) -> Dict[str, Any]:
        """
        Create a new Notion database configured for rMirror sync.

        Uses raw HTTP with initial_data_source.properties per API 2025-09-03.
        Note: status property type cannot be created via API, so we use select
        with a "Workflow" property instead. Users can manually convert to Status
        in Notion UI if desired.

        Args:
            access_token: Notion OAuth access token
            parent_page_id: Optional parent page ID (if None, creates a parent page first)
            database_title: Title for the new database
            database_type: Type of database - "notebooks" or "todos"

        Returns:
            Dict with database_id, url, and title

        Raises:
            Exception: If database creation fails
        """
        client = self._get_notion_client(access_token)

        # If no parent page specified, create one first
        # (Notion requires databases to be in a page to support custom properties)
        if not parent_page_id:
            try:
                self.logger.info("Creating rMirror parent page in workspace")
                parent_page_response = client.pages.create(
                    parent={"type": "workspace", "workspace": True},
                    properties={
                        "title": [{"type": "text", "text": {"content": "rMirror"}}]
                    },
                )
                parent_page_id = parent_page_response["id"]
                self.logger.info(f"Created parent page: {parent_page_id}")
            except Exception as e:
                self.logger.error(f"Error creating parent page: {e}")
                raise Exception(f"Failed to create parent page: {str(e)}")

        # Define parent
        parent = {"type": "page_id", "page_id": parent_page_id}

        # Define database schema based on type
        # Note: status type cannot be created via API, use select with "Workflow" instead
        if database_type == "todos":
            properties = {
                "Task": {"title": {}},  # Todo text
                "Completed": {"checkbox": {}},  # Simple completion checkbox
                "Workflow": {  # Use select since status can't be created via API
                    "select": {
                        "options": [
                            {"name": "Not started", "color": "default"},
                            {"name": "In progress", "color": "blue"},
                            {"name": "Done", "color": "green"},
                        ]
                    }
                },
                "Notebook": {"rich_text": {}},  # Source notebook name
                "Notebook UUID": {"rich_text": {}},  # For linking/deduplication
                "Page": {"number": {"format": "number"}},  # Page number where todo was found
                "Confidence": {"number": {"format": "percent"}},  # OCR confidence
                "Date Written": {"date": {}},  # When todo was written (estimated)
                "Link to Source": {"url": {}},  # Link to source notebook/page
                "Tags": {"multi_select": {}},  # Tags (e.g., "remarkable")
                "Synced At": {"date": {}},  # Last sync timestamp
                "Priority": {
                    "select": {
                        "options": [
                            {"name": "High", "color": "red"},
                            {"name": "Medium", "color": "yellow"},
                            {"name": "Low", "color": "gray"},
                        ]
                    }
                },
            }
        else:  # notebooks
            properties = {
                "Name": {"title": {}},  # Notebook name
                "UUID": {"rich_text": {}},  # Notebook UUID for deduplication
                "Path": {"rich_text": {}},  # Folder path in reMarkable
                "Tags": {"multi_select": {}},  # Tags extracted from path
                "Pages": {"number": {"format": "number"}},  # Number of pages
                "Last Opened": {"date": {}},  # When notebook was last opened on reMarkable
                "Last Modified": {"date": {}},  # When notebook was last modified on reMarkable
                "Synced At": {"date": {}},  # Last sync timestamp
                "Status": {
                    "select": {
                        "options": [
                            {"name": "Synced", "color": "green"},
                            {"name": "Pending", "color": "yellow"},
                            {"name": "Error", "color": "red"},
                        ]
                    }
                },
            }

        try:
            # Use raw HTTP to support initial_data_source (SDK doesn't support it yet)
            http_client = self._get_http_client()

            response = http_client.post(
                "https://api.notion.com/v1/databases",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Notion-Version": "2025-09-03",
                    "Content-Type": "application/json",
                },
                json={
                    "parent": parent,
                    "title": [{"type": "text", "text": {"content": database_title}}],
                    "is_inline": True,
                    "initial_data_source": {
                        "properties": properties
                    }
                }
            )

            http_client.close()
            response.raise_for_status()
            result = response.json()

            database_id = result["id"]
            self.logger.info(f"Created database with initial_data_source: {database_id}")

            return {
                "database_id": database_id,
                "url": result.get("url", ""),
                "title": database_title,
                "type": database_type,
                "created_time": result.get("created_time", ""),
            }

        except httpx.HTTPStatusError as e:
            error_body = e.response.text if hasattr(e.response, 'text') else str(e)
            logger.error(f"HTTP error creating Notion database: {error_body}")
            raise Exception(f"Failed to create Notion database: {error_body}")
        except Exception as e:
            logger.error(f"Error creating Notion database: {e}")
            raise Exception(f"Failed to create Notion database: {str(e)}")

    async def validate_database(
        self, access_token: str, database_id: str
    ) -> bool:
        """
        Validate that a database exists and is accessible.

        Args:
            access_token: Notion OAuth access token
            database_id: Database ID to validate

        Returns:
            True if database is valid and accessible, False otherwise
        """
        client = self._get_notion_client(access_token)

        try:
            client.databases.retrieve(database_id=database_id)
            return True
        except Exception as e:
            logger.error(f"Database validation failed: {e}")
            return False

    async def get_database_info(
        self, access_token: str, database_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific database.

        Args:
            access_token: Notion OAuth access token
            database_id: Database ID

        Returns:
            Dict with database info or None if not found
        """
        client = self._get_notion_client(access_token)

        try:
            response = client.databases.retrieve(database_id=database_id)

            title_parts = response.get("title", [])
            title = (
                title_parts[0].get("plain_text", "Untitled")
                if title_parts
                else "Untitled"
            )

            return {
                "database_id": response["id"],
                "title": title,
                "url": response.get("url", ""),
                "created_time": response.get("created_time", ""),
                "last_edited_time": response.get("last_edited_time", ""),
                "properties": response.get("properties", {}),
                "data_sources": response.get("data_sources", []),
            }

        except Exception as e:
            logger.error(f"Error getting database info: {e}")
            return None

    async def add_database_properties(
        self,
        access_token: str,
        database_id: str,
        database_type: str = "notebooks",
    ) -> Dict[str, Any]:
        """
        Add properties to an existing database using the new 2025-09-03 API.

        This retrieves the database's data source and updates its properties.

        Args:
            access_token: Notion OAuth access token
            database_id: Database ID to update
            database_type: Type of database - "notebooks" or "todos"

        Returns:
            Dict with success status and property info

        Raises:
            Exception: If property addition fails
        """
        client = self._get_notion_client(access_token)

        try:
            # Step 1: Get database to find data source ID
            self.logger.info(f"Retrieving database {database_id} to find data source")
            db_response = client.databases.retrieve(database_id=database_id)

            data_sources = db_response.get("data_sources", [])
            if not data_sources:
                raise Exception("No data sources found in database")

            data_source_id = data_sources[0]["id"]
            self.logger.info(f"Found data source: {data_source_id}")

            # Step 2: Define properties based on type
            # Note: status type cannot be created via API, use select with "Workflow" instead
            if database_type == "todos":
                properties = {
                    "Completed": {"checkbox": {}},
                    "Workflow": {  # Use select since status can't be created via API
                        "select": {
                            "options": [
                                {"name": "Not started", "color": "default"},
                                {"name": "In progress", "color": "blue"},
                                {"name": "Done", "color": "green"},
                            ]
                        }
                    },
                    "Notebook": {"rich_text": {}},
                    "Notebook UUID": {"rich_text": {}},
                    "Page": {"number": {"format": "number"}},
                    "Confidence": {"number": {"format": "percent"}},
                    "Date Written": {"date": {}},
                    "Link to Source": {"url": {}},
                    "Tags": {"multi_select": {}},
                    "Synced At": {"date": {}},
                    "Priority": {
                        "select": {
                            "options": [
                                {"name": "High", "color": "red"},
                                {"name": "Medium", "color": "yellow"},
                                {"name": "Low", "color": "gray"},
                            ]
                        }
                    },
                }
            else:  # notebooks
                properties = {
                    "UUID": {"rich_text": {}},
                    "Path": {"rich_text": {}},
                    "Tags": {"multi_select": {}},
                    "Pages": {"number": {"format": "number"}},
                    "Last Opened": {"date": {}},
                    "Last Modified": {"date": {}},
                    "Synced At": {"date": {}},
                    "Status": {
                        "select": {
                            "options": [
                                {"name": "Synced", "color": "green"},
                                {"name": "Pending", "color": "yellow"},
                                {"name": "Error", "color": "red"},
                            ]
                        }
                    },
                }

            # Step 3: Update data source properties using raw HTTP client
            # (notion-client library doesn't support data_sources endpoint yet)
            http_client = self._get_http_client()

            response = http_client.patch(
                f"https://api.notion.com/v1/data_sources/{data_source_id}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Notion-Version": "2025-09-03",
                    "Content-Type": "application/json",
                },
                json={"properties": properties}
            )

            http_client.close()

            response.raise_for_status()
            updated_ds = response.json()

            property_names = list(updated_ds.get("properties", {}).keys())
            self.logger.info(f"Successfully added {len(property_names)} properties: {property_names}")

            return {
                "success": True,
                "data_source_id": data_source_id,
                "properties": property_names,
                "property_count": len(property_names),
            }

        except Exception as e:
            self.logger.error(f"Error adding database properties: {e}")
            raise Exception(f"Failed to add database properties: {str(e)}")
