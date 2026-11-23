"""Tests for GET /sync/stored-pages (first-contact reconciliation by the Mac app)."""

from datetime import datetime, timedelta
from typing import Generator

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.sync import router as sync_router
from app.config import get_settings
from app.database import get_db
from app.models.notebook import Notebook
from app.models.page import Page
from app.models.user import User

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64


def _user(db: Session, n: int) -> User:
    user = User(
        email=f"stored-pages-{n}@example.com",
        full_name=f"Stored Pages {n}",
        clerk_user_id=f"clerk_stored_pages_{n}",
        is_active=True,
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _notebook(db: Session, user: User, uuid: str, deleted: bool = False) -> Notebook:
    nb = Notebook(
        user_id=user.id,
        notebook_uuid=uuid,
        visible_name=uuid,
        document_type="notebook",
        deleted=deleted,
    )
    db.add(nb)
    db.commit()
    db.refresh(nb)
    return nb


def _page(db: Session, nb: Notebook, page_uuid, file_hash, ocr_status="completed", removed=False) -> Page:
    page = Page(
        notebook_id=nb.id,
        page_uuid=page_uuid,
        file_hash=file_hash,
        ocr_status=ocr_status,
        removed_at=datetime.utcnow() if removed else None,
    )
    db.add(page)
    db.commit()
    return page


def _token(user: User, token_type: str = "agent") -> dict:
    settings = get_settings()
    claims = {"sub": str(user.id), "type": token_type, "exp": datetime.utcnow() + timedelta(days=1)}
    token = jwt.encode(claims, settings.secret_key, algorithm=settings.algorithm)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(db: Session) -> Generator[TestClient, None, None]:
    """Real auth dependencies, only the DB session is overridden."""
    app = FastAPI()
    app.include_router(sync_router, prefix="/sync")

    def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)


def test_empty_account(client, db):
    user = _user(db, 1)
    resp = client.get("/sync/stored-pages", headers=_token(user))
    assert resp.status_code == 200
    assert resp.json() == {"notebooks": [], "notebook_count": 0, "page_count": 0}


def test_pages_across_two_notebooks(client, db):
    user = _user(db, 1)
    nb1 = _notebook(db, user, "nb-1")
    nb2 = _notebook(db, user, "nb-2")
    _page(db, nb1, "p1", HASH_A)
    _page(db, nb1, "p2", HASH_B, ocr_status="pending_quota")
    _page(db, nb2, "p1", HASH_C)  # same page uuid under another notebook row

    body = client.get("/sync/stored-pages", headers=_token(user)).json()

    assert body["notebook_count"] == 2
    assert body["page_count"] == 3
    by_uuid = {n["notebook_uuid"]: n["pages"] for n in body["notebooks"]}
    assert by_uuid["nb-1"] == [
        {"page_uuid": "p1", "file_hash": HASH_A, "ocr_status": "completed"},
        {"page_uuid": "p2", "file_hash": HASH_B, "ocr_status": "pending_quota"},
    ]
    assert by_uuid["nb-2"] == [{"page_uuid": "p1", "file_hash": HASH_C, "ocr_status": "completed"}]


def test_other_users_pages_not_returned(client, db):
    me = _user(db, 1)
    other = _user(db, 2)
    _page(db, _notebook(db, me, "mine"), "p1", HASH_A)
    _page(db, _notebook(db, other, "theirs"), "p9", HASH_B)

    body = client.get("/sync/stored-pages", headers=_token(me)).json()

    assert [n["notebook_uuid"] for n in body["notebooks"]] == ["mine"]
    assert body["page_count"] == 1


def test_pages_without_uuid_or_hash_left_out(client, db):
    user = _user(db, 1)
    nb = _notebook(db, user, "nb-1")
    _page(db, nb, "ok", HASH_A)
    _page(db, nb, None, HASH_B)
    _page(db, nb, "no-hash", None)
    only_stubs = _notebook(db, user, "stubs")
    _page(db, only_stubs, "stub", None, ocr_status="not_synced")

    body = client.get("/sync/stored-pages", headers=_token(user)).json()

    assert body["notebook_count"] == 1
    assert body["page_count"] == 1
    assert body["notebooks"][0]["pages"][0]["page_uuid"] == "ok"


def test_removed_page_left_out(client, db):
    user = _user(db, 1)
    nb = _notebook(db, user, "nb-1")
    _page(db, nb, "live", HASH_A)
    _page(db, nb, "gone", HASH_B, removed=True)
    all_removed = _notebook(db, user, "all-removed")
    _page(db, all_removed, "gone2", HASH_C, removed=True)

    body = client.get("/sync/stored-pages", headers=_token(user)).json()

    assert body["notebook_count"] == 1
    assert [p["page_uuid"] for p in body["notebooks"][0]["pages"]] == ["live"]


def test_deleted_notebook_left_out(client, db):
    user = _user(db, 1)
    _page(db, _notebook(db, user, "live"), "p1", HASH_A)
    _page(db, _notebook(db, user, "deleted", deleted=True), "p2", HASH_B)

    body = client.get("/sync/stored-pages", headers=_token(user)).json()

    assert [n["notebook_uuid"] for n in body["notebooks"]] == ["live"]
    assert body["page_count"] == 1


def test_unauthenticated_is_401(client):
    assert client.get("/sync/stored-pages").status_code == 401


def test_agent_token_accepted(client, db):
    user = _user(db, 1)
    _page(db, _notebook(db, user, "nb-1"), "p1", HASH_A)
    resp = client.get("/sync/stored-pages", headers=_token(user, "agent"))
    assert resp.status_code == 200
    assert resp.json()["page_count"] == 1


def test_listed_in_openapi(client):
    schema = client.app.openapi()
    op = schema["paths"]["/sync/stored-pages"]["get"]
    assert "StoredPagesResponse" in op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
