"""Client-supplied filenames and UUIDs must be validated before use."""

import io
import os
import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.auth.clerk import get_clerk_active_user
from app.models.user import User
from tests.test_config import test_app  # noqa: F401,F811 - fixture

PAGE_UUID = "0b6d1f9e-2c55-4a39-9f5e-1d2b3c4d5e6f"
NB_UUID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
API = "/v1"


@pytest.fixture
def client_user(db, test_app, reset_rate_limiter):  # noqa: F811
    user = User(email="uuid-test@example.com", clerk_user_id="clerk_uuid_test")
    db.add(user)
    db.commit()
    db.refresh(user)

    async def _user():
        return user

    test_app.dependency_overrides[get_clerk_active_user] = _user
    with TestClient(test_app) as client:
        yield client, user
    test_app.dependency_overrides.pop(get_clerk_active_user, None)


def _snapshot(directory):
    return sorted(os.listdir(directory))


@pytest.mark.parametrize(
    "filename",
    [
        "../../tmp/x.rm",
        "a/b.rm",
        "..\\evil.rm",
        "test_page.rm",
        ".rm",
        f"{PAGE_UUID}x.rm",
        "0b6d1f9e-2c55-4a39-9f5e-1d2b3c4d5e6g.rm",
    ],
)
def test_rm_file_bad_filename_rejected(client_user, filename):
    client, _ = client_user
    tmpdir = tempfile.gettempdir()
    before = _snapshot(tmpdir)
    with patch("app.api.processing.RMConverter") as converter:
        resp = client.post(
            f"{API}/processing/rm-file",
            files={"rm_file": (filename, io.BytesIO(b"x"), "application/octet-stream")},
        )
    assert resp.status_code == 400
    converter.assert_not_called()
    assert _snapshot(tmpdir) == before


@pytest.mark.parametrize("filename", ["../x.metadata", "nb.metadata", "a/b.metadata"])
def test_metadata_bad_filename_rejected(client_user, filename):
    client, _ = client_user
    resp = client.post(
        f"{API}/processing/rm-file",
        files={
            "rm_file": (f"{PAGE_UUID}.rm", io.BytesIO(b"x"), "application/octet-stream"),
            "metadata_file": (filename, io.BytesIO(b"{}"), "application/json"),
        },
    )
    assert resp.status_code == 400


def test_upload_uses_generated_temp_path_per_request(client_user):
    """Two uploads of the same page UUID must not share a temp path."""
    client, _ = client_user
    seen = []

    def has_content(path):
        seen.append(str(path))
        return False

    with patch("app.api.processing.RMConverter") as converter, patch(
        "app.api.processing.OCRService"
    ):
        converter.return_value.has_content.side_effect = has_content
        for _ in range(2):
            resp = client.post(
                f"{API}/processing/rm-file",
                files={
                    "rm_file": (f"{PAGE_UUID.upper()}.rm", io.BytesIO(b"x"), "application/octet-stream")
                },
            )
            assert resp.status_code == 200, resp.text

    assert len(seen) == 2 and seen[0] != seen[1]
    for p in seen:
        assert os.path.dirname(p) == tempfile.gettempdir()
        assert PAGE_UUID not in p.lower()
        assert not os.path.exists(p)


def test_content_endpoint_rejects_non_uuid(client_user):
    client, _ = client_user
    resp = client.post(
        f"{API}/notebooks/not-a-uuid/content",
        files={"content_file": ("x.content", io.BytesIO(b"{}"), "application/json")},
    )
    assert resp.status_code == 400


def test_metadata_update_rejects_non_uuid(client_user):
    client, _ = client_user
    resp = client.post(
        f"{API}/processing/metadata/update",
        json={"notebook_uuid": "../../x", "visible_name": "n"},
    )
    assert resp.status_code == 422


def test_sync_metadata_skips_bad_ids_but_accepts_batch(client_user, db):
    from app.models.notebook import Notebook
    from app.models.page import Page

    client, user = client_user
    good_page = "0B6D1F9E-2C55-4A39-9F5E-1D2B3C4D5E6F"
    body = {
        "notebooks": [
            {"uuid": "../bad", "visible_name": "bad", "pages": [PAGE_UUID]},
            {
                "uuid": NB_UUID.upper(),
                "visible_name": "good",
                "pages": [good_page, "a/b"],
            },
        ]
    }
    resp = client.post(f"{API}/sync/metadata", json=body)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["notebooks_created"] == 1
    assert data["pages_registered"] == 1
    assert data["skipped"] == 2

    notebooks = db.query(Notebook).filter(Notebook.user_id == user.id).all()
    assert [n.notebook_uuid for n in notebooks] == [NB_UUID]
    pages = db.query(Page).filter(Page.notebook_id == notebooks[0].id).all()
    assert [p.page_uuid for p in pages] == [PAGE_UUID]
