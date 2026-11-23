"""The agent reads a notebook's page list the way the server does.

Newer .content files list pages in ``cPages.pages`` and mark deleted ones;
older files have a plain ``pages`` list. The server removes pages a list no
longer has, so both sides must pick the same list: ``cPages`` when it has
entries, else ``pages``.
"""

import json
from unittest.mock import MagicMock

from app.sync.metadata_sync import MetadataSync

NB = "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d"


def _page_uuids(tmp_path, content: dict) -> list[str]:
    (tmp_path / f"{NB}.content").write_text(json.dumps(content))
    sync = MetadataSync.__new__(MetadataSync)
    sync.config = MagicMock()
    sync.remarkable_folder = tmp_path
    return sync._get_page_uuids(NB)


def test_cpages_wins_over_a_stale_plain_list(tmp_path):
    content = {
        "pages": ["a", "b"],  # stale: lacks the page added later
        "cPages": {"pages": [{"id": "a"}, {"id": "b", "deleted": {"value": 1}}, {"id": "c"}]},
    }
    assert _page_uuids(tmp_path, content) == ["a", "c"]


def test_plain_list_is_used_when_cpages_is_missing_or_empty(tmp_path):
    assert _page_uuids(tmp_path, {"pages": ["a", "b"]}) == ["a", "b"]
    assert _page_uuids(tmp_path, {"pages": ["a"], "cPages": {"pages": []}}) == ["a"]
