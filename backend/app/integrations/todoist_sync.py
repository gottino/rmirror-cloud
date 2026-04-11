"""Todoist sync target implementation for rmirror Cloud."""

import logging
from typing import Any, Dict, Optional

import httpx

from app.core.sync_engine import SyncItem, SyncResult, SyncTarget
from app.models.sync_record import SyncItemType, SyncStatus

logger = logging.getLogger(__name__)

TODOIST_API_URL = "https://api.todoist.com/api/v1"


class TodoistSyncTarget(SyncTarget):
    """
    Todoist implementation for syncing todos as tasks.

    Creates tasks in a user-chosen Todoist project with
    'remarkable' and notebook-name labels.
    """

    def __init__(self, access_token: str, project_id: str):
        super().__init__("todoist")
        self.access_token = access_token
        self.project_id = project_id

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def sync_item(self, item: SyncItem) -> SyncResult:
        """Sync a todo to Todoist as a task."""
        if item.item_type != SyncItemType.TODO:
            return SyncResult(
                status=SyncStatus.SKIPPED,
                metadata={"reason": "This integration only syncs todos"},
            )

        todo_data = item.data
        todo_text = todo_data.get("text", "") or todo_data.get("todo_text", "")

        if not todo_text.strip():
            return SyncResult(
                status=SyncStatus.SKIPPED,
                metadata={"reason": "Empty todo text"},
            )

        notebook_name = todo_data.get("notebook_name", "")
        page_number = todo_data.get("page_number")

        # Build description
        description_parts = []
        if notebook_name:
            desc = f"From *{notebook_name}*"
            if page_number is not None:
                desc += f", page {page_number}"
            description_parts.append(desc)
        description = "\n".join(description_parts)

        # Build labels
        labels = ["remarkable"]
        if notebook_name:
            labels.append(notebook_name)

        payload = {
            "content": todo_text,
            "project_id": self.project_id,
            "labels": labels,
            "description": description,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{TODOIST_API_URL}/tasks",
                    headers=self._headers(),
                    json=payload,
                )

                if response.status_code == 429:
                    return SyncResult(
                        status=SyncStatus.RETRY,
                        error_message="Rate limited by Todoist",
                    )

                response.raise_for_status()
                task_data = response.json()
                task_id = str(task_data["id"])

            self.logger.info(f"Created Todoist task: {task_id} - '{todo_text[:50]}'")
            return SyncResult(
                status=SyncStatus.SUCCESS,
                target_id=task_id,
                metadata={
                    "action": "task_created",
                    "project_id": self.project_id,
                    "labels": labels,
                },
            )

        except httpx.HTTPStatusError as e:
            self.logger.error(f"Todoist API error: {e}")
            return SyncResult(status=SyncStatus.FAILED, error_message=str(e))
        except Exception as e:
            self.logger.error(f"Error syncing todo to Todoist: {e}")
            return SyncResult(status=SyncStatus.FAILED, error_message=str(e))

    async def update_item(self, external_id: str, item: SyncItem) -> SyncResult:
        """Update an existing Todoist task."""
        todo_data = item.data
        todo_text = todo_data.get("text", "") or todo_data.get("todo_text", "")
        notebook_name = todo_data.get("notebook_name", "")
        page_number = todo_data.get("page_number")

        description_parts = []
        if notebook_name:
            desc = f"From *{notebook_name}*"
            if page_number is not None:
                desc += f", page {page_number}"
            description_parts.append(desc)

        labels = ["remarkable"]
        if notebook_name:
            labels.append(notebook_name)

        payload = {
            "content": todo_text,
            "labels": labels,
            "description": "\n".join(description_parts),
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{TODOIST_API_URL}/tasks/{external_id}",
                    headers=self._headers(),
                    json=payload,
                )
                response.raise_for_status()

            self.logger.info(f"Updated Todoist task: {external_id}")
            return SyncResult(
                status=SyncStatus.SUCCESS,
                target_id=external_id,
                metadata={"action": "updated"},
            )

        except Exception as e:
            self.logger.error(f"Error updating Todoist task: {e}")
            return SyncResult(status=SyncStatus.FAILED, error_message=str(e))

    async def delete_item(self, external_id: str) -> SyncResult:
        """Delete a Todoist task."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"{TODOIST_API_URL}/tasks/{external_id}",
                    headers=self._headers(),
                )
                response.raise_for_status()

            return SyncResult(
                status=SyncStatus.SUCCESS,
                metadata={"action": "deleted"},
            )

        except Exception as e:
            return SyncResult(status=SyncStatus.FAILED, error_message=str(e))

    async def check_duplicate(self, content_hash: str) -> Optional[str]:
        """Deduplication handled by SyncRecord table, not Todoist queries."""
        return None

    def get_target_info(self) -> Dict[str, Any]:
        return {
            "target_name": self.target_name,
            "connected": True,
            "project_id": self.project_id,
            "capabilities": {"todos": True},
        }
