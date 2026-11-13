"""Request-level tests for notebook page pagination.

Covers ``GET /notebooks/{id}/pages`` and the ``include_pages`` flag and
``page_counts`` field on ``GET /notebooks/{id}``.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.api.notebooks import router as notebooks_router
from app.auth.clerk import get_clerk_active_user
from app.database import get_db
from app.models.notebook import Notebook
from app.models.notebook_page import NotebookPage
from app.models.page import Page
from app.models.user import User


def _make_client(db: Session, user: User) -> TestClient:
    app = FastAPI()
    app.include_router(notebooks_router, prefix="/notebooks")

    def _get_db():
        yield db

    async def _get_user():
        return user

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_clerk_active_user] = _get_user
    return TestClient(app)


def _create_user(db: Session, suffix: str) -> User:
    user = User(
        email=f"pages-{suffix}@example.com",
        full_name=f"Pages {suffix}",
        clerk_user_id=f"clerk_pages_{suffix}",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create_notebook(
    db: Session,
    user: User,
    num_pages: int,
    statuses: dict[int, str] | None = None,
    uuid: str = "nb-pages",
) -> Notebook:
    """Create a notebook whose pages are inserted in shuffled order.

    Insertion order differs from page order so ordering is really tested.
    """
    statuses = statuses or {}
    notebook = Notebook(
        user_id=user.id,
        notebook_uuid=uuid,
        visible_name="Paged Notebook",
        document_type="notebook",
    )
    db.add(notebook)
    db.flush()

    order = list(range(1, num_pages + 1))
    order = order[1::2] + order[0::2]  # e.g. 2,4,6,...,1,3,5,...
    for page_number in order:
        page = Page(
            notebook_id=notebook.id,
            page_uuid=f"{uuid}-page-{page_number}",
            ocr_status=statuses.get(page_number, "completed"),
            ocr_text=f"text of page {page_number}",
        )
        db.add(page)
        db.flush()
        db.add(NotebookPage(notebook_id=notebook.id, page_id=page.id, page_number=page_number))

    db.commit()
    db.refresh(notebook)
    return notebook


@pytest.fixture
def owner(db: Session) -> User:
    return _create_user(db, "owner")


@pytest.fixture
def other_user(db: Session) -> User:
    return _create_user(db, "other")


# --- GET /notebooks/{id}/pages -------------------------------------------


def test_first_window_defaults_to_50_in_page_order(db: Session, owner: User):
    nb = _create_notebook(db, owner, 120)
    client = _make_client(db, owner)

    resp = client.get(f"/notebooks/{nb.id}/pages")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 120
    assert body["offset"] == 0
    assert body["limit"] == 50
    assert body["has_more"] is True
    assert [p["page_number"] for p in body["items"]] == list(range(1, 51))
    # OCR text is included with every item
    assert body["items"][0]["ocr_text"] == "text of page 1"


def test_offset_window_and_last_window_has_more_false(db: Session, owner: User):
    nb = _create_notebook(db, owner, 120)
    client = _make_client(db, owner)

    mid = client.get(f"/notebooks/{nb.id}/pages", params={"offset": 50, "limit": 50}).json()
    assert [p["page_number"] for p in mid["items"]] == list(range(51, 101))
    assert mid["has_more"] is True

    last = client.get(f"/notebooks/{nb.id}/pages", params={"offset": 100, "limit": 50}).json()
    assert [p["page_number"] for p in last["items"]] == list(range(101, 121))
    assert last["has_more"] is False
    assert last["total"] == 120


def test_exact_boundary_has_more_false(db: Session, owner: User):
    nb = _create_notebook(db, owner, 10)
    client = _make_client(db, owner)

    body = client.get(f"/notebooks/{nb.id}/pages", params={"offset": 0, "limit": 10}).json()
    assert len(body["items"]) == 10
    assert body["has_more"] is False


def test_offset_past_end_returns_empty(db: Session, owner: User):
    nb = _create_notebook(db, owner, 5)
    client = _make_client(db, owner)

    body = client.get(f"/notebooks/{nb.id}/pages", params={"offset": 50}).json()
    assert body["items"] == []
    assert body["total"] == 5
    assert body["has_more"] is False


def test_descending_order(db: Session, owner: User):
    nb = _create_notebook(db, owner, 7)
    client = _make_client(db, owner)

    first = client.get(
        f"/notebooks/{nb.id}/pages", params={"order": "desc", "limit": 3}
    ).json()
    assert [p["page_number"] for p in first["items"]] == [7, 6, 5]
    assert first["has_more"] is True

    rest = client.get(
        f"/notebooks/{nb.id}/pages", params={"order": "desc", "offset": 3, "limit": 10}
    ).json()
    assert [p["page_number"] for p in rest["items"]] == [4, 3, 2, 1]
    assert rest["has_more"] is False


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"order": "sideways"},
    ],
)
def test_bounds_rejected(db: Session, owner: User, params):
    nb = _create_notebook(db, owner, 3)
    client = _make_client(db, owner)

    resp = client.get(f"/notebooks/{nb.id}/pages", params=params)
    assert resp.status_code == 422


def test_limit_100_allowed(db: Session, owner: User):
    nb = _create_notebook(db, owner, 150)
    client = _make_client(db, owner)

    body = client.get(f"/notebooks/{nb.id}/pages", params={"limit": 100}).json()
    assert len(body["items"]) == 100
    assert body["limit"] == 100
    assert body["has_more"] is True


def test_other_users_notebook_is_404(db: Session, owner: User, other_user: User):
    nb = _create_notebook(db, owner, 3)
    client = _make_client(db, other_user)

    resp = client.get(f"/notebooks/{nb.id}/pages")
    assert resp.status_code == 404


def test_missing_notebook_is_404(db: Session, owner: User):
    client = _make_client(db, owner)
    assert client.get("/notebooks/999999/pages").status_code == 404


def test_page_window_uses_sql_limit(db: Session, owner: User):
    """The page window is fetched with LIMIT/OFFSET in SQL, not sliced in Python."""
    nb = _create_notebook(db, owner, 30)
    client = _make_client(db, owner)

    statements: list[str] = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", _capture)
    try:
        resp = client.get(f"/notebooks/{nb.id}/pages", params={"offset": 10, "limit": 5})
    finally:
        event.remove(engine, "before_cursor_execute", _capture)

    assert resp.status_code == 200
    page_selects = [
        s for s in statements if "FROM notebook_pages" in s and "JOIN pages" in s
    ]
    assert len(page_selects) == 1
    assert "LIMIT" in page_selects[0] and "OFFSET" in page_selects[0]


# --- GET /notebooks/{id} -------------------------------------------------


def test_get_notebook_default_still_returns_all_pages(db: Session, owner: User):
    nb = _create_notebook(db, owner, 60)
    client = _make_client(db, owner)

    body = client.get(f"/notebooks/{nb.id}").json()
    assert [p["page_number"] for p in body["pages"]] == list(range(1, 61))


def test_get_notebook_without_pages_returns_counts(db: Session, owner: User):
    nb = _create_notebook(
        db,
        owner,
        6,
        statuses={1: "not_synced", 2: "not_synced", 3: "pending_quota"},
    )
    client = _make_client(db, owner)

    resp = client.get(f"/notebooks/{nb.id}", params={"include_pages": "false"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["pages"] == []
    assert body["visible_name"] == "Paged Notebook"
    assert body["page_counts"] == {
        "total_pages": 6,
        "synced_pages": 4,
        "not_synced_pages": 2,
        "pending_quota_pages": 1,
    }


def test_get_notebook_with_pages_also_returns_counts(db: Session, owner: User):
    nb = _create_notebook(db, owner, 4, statuses={4: "not_synced"})
    client = _make_client(db, owner)

    body = client.get(f"/notebooks/{nb.id}").json()
    assert len(body["pages"]) == 4
    assert body["page_counts"]["total_pages"] == 4
    assert body["page_counts"]["not_synced_pages"] == 1


def test_get_notebook_without_pages_other_user_is_404(
    db: Session, owner: User, other_user: User
):
    nb = _create_notebook(db, owner, 3)
    client = _make_client(db, other_user)

    resp = client.get(f"/notebooks/{nb.id}", params={"include_pages": "false"})
    assert resp.status_code == 404
