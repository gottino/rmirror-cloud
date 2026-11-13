"""Hot read/write paths must issue a number of SQL statements that does not grow
with the number of rows (no N+1 queries).

Statements are counted with SQLAlchemy's ``before_cursor_execute`` event.
"""

import uuid
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.auth.clerk import get_clerk_active_user
from app.models.notebook import Notebook
from app.models.notebook_page import NotebookPage
from app.models.page import Page
from app.models.user import User
from tests.test_config import test_app  # noqa: F401,F811 - fixture

API = "/v1"


@contextmanager
def count_statements(engine):
    statements = []

    def _before(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _before)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", _before)


@pytest.fixture
def client_user(db, test_app):  # noqa: F811
    user = User(email="query-count@example.com", clerk_user_id="clerk_query_count")
    db.add(user)
    db.commit()
    db.refresh(user)

    async def _user():
        return user

    test_app.dependency_overrides[get_clerk_active_user] = _user
    with TestClient(test_app) as client:
        yield client, user
    test_app.dependency_overrides.pop(get_clerk_active_user, None)


# ---------------------------------------------------------------------------
# GET /notebooks/tree
# ---------------------------------------------------------------------------


def _add_notebook(db, user, name, statuses, texts=None, document_type="notebook", parent_uuid=None):
    """Add a notebook whose pages (1..n) have the given OCR statuses and texts."""
    nb = Notebook(
        user_id=user.id,
        notebook_uuid=str(uuid.uuid4()),
        visible_name=name,
        document_type=document_type,
        parent_uuid=parent_uuid,
    )
    db.add(nb)
    db.flush()
    texts = texts or [None] * len(statuses)
    for number, (status, text) in enumerate(zip(statuses, texts), start=1):
        page = Page(notebook_id=nb.id, page_uuid=str(uuid.uuid4()), ocr_status=status, ocr_text=text)
        db.add(page)
        db.flush()
        db.add(NotebookPage(notebook_id=nb.id, page_id=page.id, page_number=number))
    db.flush()
    return nb


def _seed_tree(db, user, extra_notebooks):
    folder = _add_notebook(db, user, "Folder", [], document_type="folder")
    nbs = {
        # Latest page has text: preview from it.
        "latest_text": _add_notebook(
            db, user, "A", ["completed", "completed"], ["old text", "  new text  "], parent_uuid=folder.notebook_uuid
        ),
        # Latest page has no text but is completed: preview from an earlier page.
        "earlier_text": _add_notebook(db, user, "B", ["completed", "completed"], ["x" * 150, ""]),
        # Latest page is not synced: no preview even though page 1 has text.
        "not_synced": _add_notebook(db, user, "C", ["completed", "not_synced"], ["hidden", None]),
        # Latest page waits for quota.
        "pending_quota": _add_notebook(db, user, "D", ["completed", "pending_quota", "pending_quota"], ["t", None, None]),
        # No pages at all.
        "empty": _add_notebook(db, user, "E", []),
        # Not a notebook: no sync progress.
        "pdf": _add_notebook(db, user, "F", ["completed"], ["pdf text"], document_type="pdf"),
    }
    for i in range(extra_notebooks):
        _add_notebook(db, user, f"Extra {i:03d}", ["completed", "not_synced", "pending_quota"], ["e", None, None])
    db.commit()
    return folder, nbs


def _nodes_by_uuid(tree):
    out = {}
    stack = list(tree)
    while stack:
        node = stack.pop()
        out[node["notebook_uuid"]] = node
        stack.extend(node["children"])
    return out


def test_tree_previews_and_progress(client_user, db):
    client, user = client_user
    folder, nbs = _seed_tree(db, user, extra_notebooks=0)

    resp = client.get(f"{API}/notebooks/tree")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 7
    nodes = _nodes_by_uuid(body["tree"])

    folder_node = nodes[folder.notebook_uuid]
    assert folder_node["is_folder"] is True
    assert [c["visible_name"] for c in folder_node["children"]] == ["A"]
    assert folder_node["sync_progress"] is None and folder_node["preview"] is None

    def node(key):
        return nodes[nbs[key].notebook_uuid]

    assert node("latest_text")["preview"] == "new text"
    assert node("latest_text")["sync_progress"] == {
        "total_pages": 2, "synced_pages": 2, "not_synced_pages": 0, "pending_quota_pages": 0,
    }
    assert node("earlier_text")["preview"] == "x" * 100 + "..."
    assert node("not_synced")["preview"] is None
    assert node("not_synced")["sync_progress"] == {
        "total_pages": 2, "synced_pages": 1, "not_synced_pages": 1, "pending_quota_pages": 0,
    }
    assert node("pending_quota")["preview"] is None
    assert node("pending_quota")["sync_progress"] == {
        "total_pages": 3, "synced_pages": 3, "not_synced_pages": 0, "pending_quota_pages": 2,
    }
    assert node("empty")["preview"] is None
    assert node("empty")["sync_progress"] == {
        "total_pages": 0, "synced_pages": 0, "not_synced_pages": 0, "pending_quota_pages": 0,
    }
    assert node("pdf")["preview"] is None and node("pdf")["sync_progress"] is None


def test_tree_query_count_is_constant(client_user, db, db_engine):
    client, user = client_user
    _seed_tree(db, user, extra_notebooks=2)
    with count_statements(db_engine) as few:
        assert client.get(f"{API}/notebooks/tree").status_code == 200

    _seed_tree(db, user, extra_notebooks=40)
    with count_statements(db_engine) as many:
        resp = client.get(f"{API}/notebooks/tree")
    assert resp.status_code == 200
    assert resp.json()["total"] == 7 + 2 + 7 + 40

    assert len(many) == len(few), many
    assert len(many) <= 5


# ---------------------------------------------------------------------------
# POST /sync/metadata
# ---------------------------------------------------------------------------


def _uuid(prefix, i):
    return f"{prefix:08x}-0000-4000-8000-{i:012x}"


def _metadata_body(notebooks, pages_per_notebook, name="n"):
    return {
        "notebooks": [
            {
                "uuid": _uuid(n + 1, 0),
                "visible_name": f"{name} {n}",
                "pages": [_uuid(n + 1, p + 1) for p in range(pages_per_notebook)],
                "last_opened": "2026-01-02T03:04:05Z",
            }
            for n in range(notebooks)
        ]
    }


@pytest.mark.parametrize("notebooks,pages_per_notebook", [(1, 1000), (10, 100)])
def test_metadata_sync_1000_pages_under_20_statements(client_user, db_engine, notebooks, pages_per_notebook):
    client, _ = client_user
    body = _metadata_body(notebooks, pages_per_notebook)

    # First sync: everything is new.
    with count_statements(db_engine) as first:
        resp = client.post(f"{API}/sync/metadata", json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["notebooks_created"] == notebooks
    assert resp.json()["pages_registered"] == 1000
    assert len(first) < 20, first

    # Second sync of the same library, pages reordered: everything exists.
    for nb in body["notebooks"]:
        nb["pages"].reverse()
    with count_statements(db_engine) as second:
        resp = client.post(f"{API}/sync/metadata", json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["notebooks_updated"] == notebooks
    assert len(second) < 20, second


def test_metadata_sync_statement_count_does_not_grow(client_user, db_engine):
    client, _ = client_user
    small = _metadata_body(2, 3)
    with count_statements(db_engine) as small_first:
        assert client.post(f"{API}/sync/metadata", json=small).status_code == 200
    for nb in small["notebooks"]:
        nb["pages"].reverse()
    with count_statements(db_engine) as small_again:
        assert client.post(f"{API}/sync/metadata", json=small).status_code == 200

    # A different user-visible library of 40 notebooks x 25 pages (new uuids).
    big = _metadata_body(40, 25)
    for nb in big["notebooks"]:
        nb["uuid"] = nb["uuid"].replace("-0000-4000-", "-1111-4000-")
        nb["pages"] = [p.replace("-0000-4000-", "-1111-4000-") for p in nb["pages"]]
    with count_statements(db_engine) as large:
        assert client.post(f"{API}/sync/metadata", json=big).status_code == 200
    for nb in big["notebooks"]:
        nb["pages"].reverse()
    with count_statements(db_engine) as large_again:
        assert client.post(f"{API}/sync/metadata", json=big).status_code == 200

    assert len(large) == len(small_first)
    assert len(large_again) == len(small_again)


def test_metadata_sync_results(client_user, db):
    """Create, update, reorder and status handling of the bulk path."""
    client, user = client_user
    nb_uuid = _uuid(1, 0)
    p1, p2, p3 = _uuid(1, 1), _uuid(1, 2), _uuid(1, 3)

    resp = client.post(
        f"{API}/sync/metadata",
        json={"notebooks": [{
            "uuid": nb_uuid, "visible_name": "First", "pages": [p1, p2],
            "pinned": True, "version": 3, "last_opened": "2026-01-02T03:04:05Z", "last_opened_page": 1,
        }]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "success": True, "notebooks_created": 1, "notebooks_updated": 0,
        "pages_registered": 2, "pages_already_synced": 0, "skipped": 0,
        "message": "Synced 1 notebooks with 2 pages",
    }

    nb = db.query(Notebook).filter_by(user_id=user.id, notebook_uuid=nb_uuid).one()
    pages = {p.page_uuid: p for p in db.query(Page).filter_by(notebook_id=nb.id)}
    assert set(pages) == {p1, p2}
    assert all(p.ocr_status == "not_synced" for p in pages.values())

    # p1 got content uploaded; p2 failed OCR earlier (gets reset to not_synced).
    pages[p1].s3_key = "k1"
    pages[p1].ocr_status = "completed"
    pages[p2].ocr_status = "failed"
    db.commit()

    # Second sync: reorder, add p3, change name; optional fields omitted keep values.
    resp = client.post(
        f"{API}/sync/metadata",
        json={"notebooks": [{"uuid": nb_uuid.upper(), "visible_name": "Renamed", "pages": [p3, p2, p1]}]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert (data["notebooks_created"], data["notebooks_updated"]) == (0, 1)
    assert (data["pages_registered"], data["pages_already_synced"]) == (2, 1)

    db.expire_all()
    nb = db.query(Notebook).filter_by(user_id=user.id, notebook_uuid=nb_uuid).one()
    assert nb.visible_name == "Renamed"
    assert nb.pinned is True and nb.version == 3 and nb.last_opened_page == 1
    assert nb.last_opened is not None
    assert '"pageCount": 3' in nb.content_json
    assert db.query(Notebook).filter_by(user_id=user.id).count() == 1

    order = {
        page.page_uuid: np_.page_number
        for np_, page in db.query(NotebookPage, Page).join(Page, NotebookPage.page_id == Page.id)
        .filter(NotebookPage.notebook_id == nb.id)
    }
    assert order == {p3: 1, p2: 2, p1: 3}
    statuses = {p.page_uuid: p.ocr_status for p in db.query(Page).filter_by(notebook_id=nb.id)}
    assert statuses == {p1: "completed", p2: "not_synced", p3: "not_synced"}


def test_metadata_sync_repeated_entries_in_one_request(client_user, db):
    """A notebook or page listed twice is created once; later entries update it."""
    client, user = client_user
    nb_uuid, p1, p2 = _uuid(7, 0), _uuid(7, 1), _uuid(7, 2)
    body = {"notebooks": [
        {"uuid": nb_uuid, "visible_name": "one", "pages": [p1, p2, p1], "pinned": True},
        {"uuid": nb_uuid, "visible_name": "two", "pages": [p2]},
    ]}
    resp = client.post(f"{API}/sync/metadata", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert (data["notebooks_created"], data["notebooks_updated"]) == (1, 1)
    assert data["pages_registered"] == 4

    nb = db.query(Notebook).filter_by(user_id=user.id).one()
    assert nb.visible_name == "two" and nb.pinned is True
    assert '"pageCount": 1' in nb.content_json
    assert db.query(Page).filter_by(notebook_id=nb.id).count() == 2
    order = {
        page.page_uuid: np_.page_number
        for np_, page in db.query(NotebookPage, Page).join(Page, NotebookPage.page_id == Page.id)
        .filter(NotebookPage.notebook_id == nb.id)
    }
    assert order == {p1: 3, p2: 1}
