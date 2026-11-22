"""POST /sync/metadata on PostgreSQL: page reorder/removal and concurrent syncs.

Needs a PostgreSQL database migrated to head; set ``TEST_POSTGRES_URL`` to it.
Skipped otherwise (the default SQLite unit run). The CI job
``backend-migrations`` runs it after ``alembic upgrade head``.

``notebook_pages`` is unique on (notebook_id, page_number) and on
(notebook_id, page_id). Renumbering mapping rows one by one collides with a
row that still holds the wanted number, so a reorder or a removed middle page
must not fail. Two syncs of the same notebook at the same time must neither
fail nor leave duplicate notebooks, pages or mappings.
"""

import os
import threading
import uuid
from datetime import datetime

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.sync import _apply_metadata_sync
from app.auth.clerk import get_clerk_active_user
from app.database import get_db
from app.models.notebook import Notebook
from app.models.notebook_page import NotebookPage
from app.models.page import Page
from app.models.user import User
from tests.test_config import create_test_app

POSTGRES_URL = os.environ.get("TEST_POSTGRES_URL")

pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="TEST_POSTGRES_URL not set")


@pytest.fixture
def pg():
    engine = sa.create_engine(POSTGRES_URL)
    Session = sessionmaker(bind=engine)
    email = f"metadata-sync-{uuid.uuid4().hex}@example.com"
    with engine.begin() as conn:
        user_id = conn.execute(
            sa.text(
                "INSERT INTO users (email, is_active, is_verified, subscription_tier, "
                "onboarding_state, agent_token_version, created_at, updated_at) VALUES "
                "(:email, true, true, 'free', 'signed_up', 0, :now, :now) RETURNING id"
            ),
            {"email": email, "now": datetime.utcnow()},
        ).scalar_one()
    with Session() as s:
        user = s.get(User, user_id)
        s.expunge(user)

    app = create_test_app()

    def _db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    async def _user():
        return user

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_clerk_active_user] = _user
    with TestClient(app) as client:
        yield client, Session, user_id
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM notebooks WHERE user_id = :id"), {"id": user_id})
        conn.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": user_id})
    engine.dispose()


def _body(nb_uuid, pages, name="nb"):
    return {"notebooks": [{"uuid": nb_uuid, "visible_name": name, "pages": pages}]}


def _order(Session, user_id, nb_uuid):
    with Session() as s:
        nb = s.query(Notebook).filter_by(user_id=user_id, notebook_uuid=nb_uuid).one()
        rows = (
            s.query(Page.page_uuid, NotebookPage.page_number)
            .join(NotebookPage, NotebookPage.page_id == Page.id)
            .filter(NotebookPage.notebook_id == nb.id)
            .all()
        )
    return dict(rows)


def _new_ids(n):
    return [str(uuid.uuid4()) for _ in range(n)]


def test_reorder_two_pages(pg):
    client, Session, user_id = pg
    nb, a, b, c = _new_ids(4)
    assert client.post("/v1/sync/metadata", json=_body(nb, [a, b, c])).status_code == 200

    resp = client.post("/v1/sync/metadata", json=_body(nb, [b, a, c]))
    assert resp.status_code == 200, resp.text
    assert _order(Session, user_id, nb) == {b: 1, a: 2, c: 3}


def test_reverse_many_pages(pg):
    client, Session, user_id = pg
    nb, *pages = _new_ids(51)
    assert client.post("/v1/sync/metadata", json=_body(nb, pages)).status_code == 200

    resp = client.post("/v1/sync/metadata", json=_body(nb, pages[::-1]))
    assert resp.status_code == 200, resp.text
    assert _order(Session, user_id, nb) == {p: i for i, p in enumerate(pages[::-1], start=1)}


def test_remove_middle_page(pg):
    client, Session, user_id = pg
    nb, a, b, c = _new_ids(4)
    assert client.post("/v1/sync/metadata", json=_body(nb, [a, b, c])).status_code == 200

    resp = client.post("/v1/sync/metadata", json=_body(nb, [a, c]))
    assert resp.status_code == 200, resp.text
    assert _order(Session, user_id, nb) == {a: 1, c: 2}


def _run_concurrently(Session, user_id, client, nb, pages_a, pages_b):
    """Transaction A writes and stays open while request B syncs the same notebook."""
    from app.api.sync import NotebookMetadataItem

    session_a = Session()
    item = NotebookMetadataItem(uuid=nb, visible_name="A", pages=pages_a)
    _apply_metadata_sync(session_a, user_id, [(nb, item, pages_a)])

    outcome = {}

    def request_b():
        try:
            outcome["resp"] = client.post("/v1/sync/metadata", json=_body(nb, pages_b, name="B"))
        except Exception as exc:  # reported by the assertion below
            outcome["error"] = exc

    thread = threading.Thread(target=request_b)
    thread.start()
    thread.join(timeout=2)  # B is either blocked on A's rows or already done
    session_a.commit()
    session_a.close()
    thread.join(timeout=30)
    assert not thread.is_alive()
    assert "error" not in outcome, outcome.get("error")
    assert outcome["resp"].status_code == 200, outcome["resp"].text


def _assert_single_rows(Session, user_id, nb, pages):
    with Session() as s:
        notebooks = s.query(Notebook).filter_by(user_id=user_id, notebook_uuid=nb).all()
        assert len(notebooks) == 1
        page_rows = s.query(Page).filter_by(notebook_id=notebooks[0].id).all()
        assert sorted(p.page_uuid for p in page_rows) == sorted(pages)
        mappings = s.query(NotebookPage).filter_by(notebook_id=notebooks[0].id).all()
        assert len(mappings) == len(pages)


def test_concurrent_first_sync_of_same_notebook(pg):
    client, Session, user_id = pg
    nb, *pages = _new_ids(4)
    _run_concurrently(Session, user_id, client, nb, pages, pages)
    _assert_single_rows(Session, user_id, nb, pages)
    assert _order(Session, user_id, nb) == {p: i for i, p in enumerate(pages, start=1)}


def test_concurrent_reorder_of_same_notebook(pg):
    client, Session, user_id = pg
    nb, *pages = _new_ids(4)
    assert client.post("/v1/sync/metadata", json=_body(nb, pages)).status_code == 200
    _run_concurrently(Session, user_id, client, nb, pages[::-1], pages[::-1])
    _assert_single_rows(Session, user_id, nb, pages)
    assert _order(Session, user_id, nb) == {p: i for i, p in enumerate(pages[::-1], start=1)}
