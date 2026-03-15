"""Tests for Obsidian sync change detection."""

from unittest.mock import MagicMock, patch

from app.api.obsidian import _get_changed_notebooks


class TestGetChangedNotebooks:
    """Tests for _get_changed_notebooks helper."""

    def _make_notebook(self, id, notebook_uuid, content_hash, deleted=False):
        nb = MagicMock()
        nb.id = id
        nb.notebook_uuid = notebook_uuid
        nb.obsidian_content_hash = content_hash
        nb.deleted = deleted
        return nb

    def _make_sync_record(self, page_uuid, content_hash):
        sr = MagicMock()
        sr.page_uuid = page_uuid
        sr.content_hash = content_hash
        return sr

    @patch("app.api.obsidian.SyncRecord")
    @patch("app.api.obsidian.Notebook")
    def test_new_notebook_included(self, mock_notebook, mock_sync_record):
        """A notebook with content hash but no sync record should be included."""
        mock_db = MagicMock()
        nb = self._make_notebook(1, "uuid-1", "hash-abc")

        # First query: notebooks
        notebooks_query = MagicMock()
        notebooks_query.filter.return_value = notebooks_query
        notebooks_query.order_by.return_value = notebooks_query
        notebooks_query.limit.return_value = notebooks_query
        notebooks_query.all.return_value = [nb]

        # Second query: sync records (none exist)
        sync_query = MagicMock()
        sync_query.filter.return_value = sync_query
        sync_query.all.return_value = []

        # Third query: deleted notebooks with sync records
        deleted_query = MagicMock()
        deleted_query.join.return_value = deleted_query
        deleted_query.filter.return_value = deleted_query
        deleted_query.all.return_value = []

        mock_db.query.side_effect = [notebooks_query, sync_query, deleted_query]

        changed, deleted_uuids, has_more, next_cursor = _get_changed_notebooks(
            mock_db, user_id=1, limit=50
        )

        assert len(changed) == 1
        assert changed[0].notebook_uuid == "uuid-1"
        assert deleted_uuids == []
        assert has_more is False
        assert next_cursor is None

    @patch("app.api.obsidian.SyncRecord")
    @patch("app.api.obsidian.Notebook")
    def test_unchanged_notebook_skipped(self, mock_notebook, mock_sync_record):
        """A notebook whose content hash matches sync record should be skipped."""
        mock_db = MagicMock()
        nb = self._make_notebook(1, "uuid-1", "hash-abc")

        # First query: notebooks
        notebooks_query = MagicMock()
        notebooks_query.filter.return_value = notebooks_query
        notebooks_query.order_by.return_value = notebooks_query
        notebooks_query.limit.return_value = notebooks_query
        notebooks_query.all.return_value = [nb]

        # Second query: sync record with matching hash
        sr = self._make_sync_record("uuid-1", "hash-abc")
        sync_query = MagicMock()
        sync_query.filter.return_value = sync_query
        sync_query.all.return_value = [sr]

        # Third query: deleted notebooks
        deleted_query = MagicMock()
        deleted_query.join.return_value = deleted_query
        deleted_query.filter.return_value = deleted_query
        deleted_query.all.return_value = []

        mock_db.query.side_effect = [notebooks_query, sync_query, deleted_query]

        changed, deleted_uuids, has_more, next_cursor = _get_changed_notebooks(
            mock_db, user_id=1, limit=50
        )

        assert len(changed) == 0
        assert deleted_uuids == []
