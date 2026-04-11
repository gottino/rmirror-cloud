"""Todoist OAuth service for handling OAuth flow and project operations."""

import logging
from typing import Any, Dict, List
from urllib.parse import urlencode

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

TODOIST_AUTH_URL = "https://todoist.com/oauth/authorize"
TODOIST_TOKEN_URL = "https://todoist.com/oauth/access_token"
TODOIST_API_URL = "https://api.todoist.com/rest/v2"


class TodoistOAuthService:
    """Service for handling Todoist OAuth flow and project operations."""

    def __init__(self):
        settings = get_settings()
        self.client_id = settings.todoist_client_id
        self.client_secret = settings.todoist_client_secret
        self.redirect_uri = settings.todoist_redirect_uri
        self.logger = logger

        if not all([self.client_id, self.client_secret, self.redirect_uri]):
            logger.warning("Todoist OAuth credentials not configured")

    def get_authorization_url(self, state: str) -> str:
        """Generate Todoist OAuth authorization URL."""
        params = {
            "client_id": self.client_id,
            "scope": "data:read,data:read_write,task:add",
            "state": state,
        }
        return f"{TODOIST_AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """Exchange authorization code for access token."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                TODOIST_TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": self.redirect_uri,
                },
            )
            response.raise_for_status()
            return response.json()

    async def list_projects(self, access_token: str) -> List[Dict[str, Any]]:
        """List all projects for the authenticated user."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{TODOIST_API_URL}/projects",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            return response.json()

    async def create_project(self, access_token: str, name: str) -> Dict[str, Any]:
        """Create a new Todoist project."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{TODOIST_API_URL}/projects",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={"name": name},
            )
            response.raise_for_status()
            return response.json()
