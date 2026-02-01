"""Notebook metadata service for building folder hierarchies and paths."""

import logging
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.models.notebook import Notebook

logger = logging.getLogger(__name__)


class NotebookMetadataService:
    """Service for managing notebook metadata and folder hierarchies."""

    def __init__(self, db: Session, user_id: int):
        """
        Initialize the metadata service.

        Args:
            db: Database session
            user_id: User ID to scope operations
        """
        self.db = db
        self.user_id = user_id
        self._path_cache: Dict[str, str] = {}

    def build_path(self, notebook_uuid: str) -> str:
        """
        Build the full folder path for a notebook by traversing parent chain.

        Args:
            notebook_uuid: UUID of the notebook

        Returns:
            Full path like "Work/Projects/Meeting Notes"
        """
        # Check cache first
        if notebook_uuid in self._path_cache:
            return self._path_cache[notebook_uuid]

        # Find the notebook
        notebook = (
            self.db.query(Notebook)
            .filter(
                Notebook.user_id == self.user_id,
                Notebook.notebook_uuid == notebook_uuid,
            )
            .first()
        )

        if not notebook:
            logger.warning(f"Notebook {notebook_uuid} not found")
            return f"<UNKNOWN>/{notebook_uuid}"

        # Base case: no parent (root level)
        if not notebook.parent_uuid or notebook.parent_uuid == "":
            path = notebook.visible_name
        elif notebook.parent_uuid == "trash":
            # Special case: trashed items
            path = f"🗑️ Trash/{notebook.visible_name}"
        else:
            # Recursive case: get parent path and append this notebook's name
            parent_path = self.build_path(notebook.parent_uuid)
            if parent_path.startswith("<UNKNOWN>"):
                # Parent not found, treat as root level
                path = f"📁 {notebook.visible_name}"
            else:
                path = f"{parent_path}/{notebook.visible_name}"

        # Cache the result
        self._path_cache[notebook_uuid] = path
        return path

    def update_notebook_paths(self) -> int:
        """
        Update full_path for all notebooks belonging to this user.

        Returns:
            Number of notebooks updated
        """
        logger.info(f"Updating notebook paths for user {self.user_id}")

        # Clear cache
        self._path_cache.clear()

        # Get all notebooks for this user
        notebooks = (
            self.db.query(Notebook)
            .filter(Notebook.user_id == self.user_id)
            .all()
        )

        updated_count = 0
        for notebook in notebooks:
            # Build and update path
            new_path = self.build_path(notebook.notebook_uuid)
            if notebook.full_path != new_path:
                notebook.full_path = new_path
                updated_count += 1

        if updated_count > 0:
            self.db.commit()
            logger.info(f"Updated paths for {updated_count} notebooks")

        return updated_count

    def update_single_notebook_metadata(
        self,
        notebook_uuid: str,
        visible_name: str,
        parent_uuid: Optional[str],
        document_type: str,
        metadata: Optional[dict] = None,
    ) -> Notebook:
        """
        Update or create a notebook with metadata, then update its path.

        Args:
            notebook_uuid: UUID of the notebook
            visible_name: Display name
            parent_uuid: Parent folder UUID (None or "" for root)
            document_type: Type of document (notebook, pdf, epub, folder)
            metadata: Optional dict with additional metadata fields

        Returns:
            Updated or created Notebook instance
        """
        # Find existing notebook
        notebook = (
            self.db.query(Notebook)
            .filter(
                Notebook.user_id == self.user_id,
                Notebook.notebook_uuid == notebook_uuid,
            )
            .first()
        )

        if notebook:
            # Update existing
            notebook.visible_name = visible_name
            notebook.parent_uuid = parent_uuid if parent_uuid else None
            notebook.document_type = document_type
        else:
            # Create new
            notebook = Notebook(
                user_id=self.user_id,
                notebook_uuid=notebook_uuid,
                visible_name=visible_name,
                parent_uuid=parent_uuid if parent_uuid else None,
                document_type=document_type,
            )
            self.db.add(notebook)

        # Update optional metadata fields if provided
        if metadata:
            if "pinned" in metadata:
                notebook.pinned = metadata["pinned"]
            if "deleted" in metadata:
                notebook.deleted = metadata["deleted"]
            if "version" in metadata:
                notebook.version = metadata["version"]
            # Note: last_modified from reMarkable is stored in metadata_json, not updated_at
            # updated_at auto-updates on commit, so we can't use it for reMarkable timestamps
            if "last_opened" in metadata:
                if isinstance(metadata["last_opened"], str):
                    try:
                        notebook.last_opened = datetime.fromisoformat(
                            metadata["last_opened"].replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass
            if "last_opened_page" in metadata:
                notebook.last_opened_page = metadata["last_opened_page"]
            if "authors" in metadata:
                notebook.author = metadata["authors"]
            if "publisher" in metadata:
                notebook.publisher = metadata["publisher"]
            if "publication_date" in metadata:
                notebook.publication_date = metadata["publication_date"]

        self.db.flush()  # Get the ID without committing

        # Clear path cache and rebuild for this notebook
        self._path_cache.clear()
        notebook.full_path = self.build_path(notebook_uuid)

        self.db.commit()
        self.db.refresh(notebook)

        logger.info(
            f"Updated metadata for {visible_name} ({notebook_uuid[:8]}...) "
            f"- Path: {notebook.full_path}"
        )

        return notebook

    def update_paths_for_subtree(self, parent_uuid: str) -> int:
        """
        Update paths for a notebook and all its descendants.

        Useful when a folder is renamed or moved.

        Args:
            parent_uuid: UUID of the parent whose children need path updates

        Returns:
            Number of notebooks updated
        """
        # Clear cache
        self._path_cache.clear()

        # Find all descendants recursively
        def get_descendants(uuid: str) -> list[Notebook]:
            children = (
                self.db.query(Notebook)
                .filter(
                    Notebook.user_id == self.user_id,
                    Notebook.parent_uuid == uuid,
                )
                .all()
            )

            descendants = list(children)
            for child in children:
                descendants.extend(get_descendants(child.notebook_uuid))

            return descendants

        # Get all affected notebooks
        affected = get_descendants(parent_uuid)

        # Update paths
        updated_count = 0
        for notebook in affected:
            new_path = self.build_path(notebook.notebook_uuid)
            if notebook.full_path != new_path:
                notebook.full_path = new_path
                updated_count += 1

        if updated_count > 0:
            self.db.commit()
            logger.info(f"Updated paths for {updated_count} notebooks in subtree")

        return updated_count
