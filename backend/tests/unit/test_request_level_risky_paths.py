"""Request-level tests for the risky endpoints, with real inputs where possible.

- POST /processing/rm-file with a REAL reMarkable ``.rm`` page: the real
  converter parses it and renders SVG; only OCR, storage and the external
  ``rsvg-convert`` binary (SVG -> PDF) are faked (a second test runs the whole
  chain when the binary is installed).
- POST /sync/metadata end to end on SQLite: stubs, page order, re-sync, skips.
- GET /notebooks/tree after a metadata sync and after an upload.
- /waitlist: invite validation and the admin approve flow.
"""

import io
import shutil
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.waitlist import WaitlistEntry, _create_invite_token
from app.auth.clerk import get_clerk_active_user, get_clerk_session_user
from app.config import get_settings
from app.core.rm_converter import RMConverter
from app.dependencies import get_storage_service
from app.models.notebook import Notebook
from app.models.notebook_page import NotebookPage
from app.models.page import OcrStatus, Page
from app.models.quota_usage import QuotaType, QuotaUsage
from app.models.user import User
from tests.conftest import create_user_with_quota
from tests.test_config import test_app  # noqa: F401 - fixture

API = "/v1"
FIXTURES = Path(__file__).parent.parent / "fixtures"
PAGE_UUID = "5d0c6e2a-8b1f-4c3d-9e7a-2f4b6c8d0e1a"
NB_UUID = "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d"
OCTET = "application/octet-stream"


def _uuid(prefix: int, i: int) -> str:
    return f"{prefix:08x}-0000-4000-8000-{i:012x}"


@pytest.fixture
def api(db, test_app, reset_rate_limiter):  # noqa: F811
    """(client, user, storage): the user is both the session and the upload user."""
    user = create_user_with_quota(db, email="risky@example.com", used=0, limit=30)
    user.clerk_user_id = "clerk_risky"
    db.commit()

    stored: dict[str, bytes] = {}
    storage = MagicMock()

    async def _upload(stream, key, content_type=None):
        stored[key] = stream.read()

    storage.upload_file = AsyncMock(side_effect=_upload)
    storage.stored = stored

    async def _user():
        return user

    test_app.dependency_overrides[get_storage_service] = lambda: storage
    test_app.dependency_overrides[get_clerk_active_user] = _user
    test_app.dependency_overrides[get_clerk_session_user] = _user
    with patch("app.services.quota_service.get_email_service"), TestClient(test_app) as client:
        yield client, user, storage
    for dep in (get_storage_service, get_clerk_active_user, get_clerk_session_user):
        test_app.dependency_overrides.pop(dep, None)


def _upload_page(client, rm_bytes, filename=f"{PAGE_UUID}.rm"):
    return client.post(
        f"{API}/processing/rm-file",
        files={
            "rm_file": (filename, io.BytesIO(rm_bytes), OCTET),
            "metadata_file": (
                f"{NB_UUID}.metadata",
                io.BytesIO(b'{"visibleName": "Real notebook", "type": "DocumentType"}'),
                "application/json",
            ),
        },
    )


# ---------------------------------------------------------------------------
# POST /processing/rm-file with a real .rm file
# ---------------------------------------------------------------------------


def test_real_rm_file_is_rendered_ocrd_and_stored(db, api):
    """Real parse + real SVG rendering; only OCR, storage and rsvg-convert are faked."""
    client, user, storage = api
    rm_bytes = (FIXTURES / "page_3.rm").read_bytes()
    seen: dict = {}

    def fake_pdf(self, svg):
        seen["svg"] = svg
        return b"%PDF-1.4 rendered"

    ocr = MagicMock()
    ocr.extract_text_from_pdf = AsyncMock(return_value="hello from the page")

    with patch.object(RMConverter, "svg_to_pdf_bytes", fake_pdf), patch(
        "app.api.processing.OCRService", return_value=ocr
    ):
        resp = _upload_page(client, rm_bytes)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["extracted_text"] == "hello from the page"
    assert body["page_count"] == 1
    assert body["metadata"]["visible_name"] == "Real notebook"

    # The real converter rendered the strokes of the file into the SVG.
    assert "<svg" in seen["svg"] and seen["svg"].count("<polyline") > 10
    ocr.extract_text_from_pdf.assert_awaited_once_with(b"%PDF-1.4 rendered")

    # Original bytes and the PDF were stored under the user/notebook/page keys.
    base = f"users/{user.id}/notebooks/{NB_UUID}/pages/{PAGE_UUID}"
    assert storage.stored[f"{base}.rm"] == rm_bytes
    assert storage.stored[f"{base}.pdf"] == b"%PDF-1.4 rendered"

    db.expire_all()
    page = db.query(Page).filter_by(page_uuid=PAGE_UUID).one()
    assert page.id == body["page_id"]
    assert page.ocr_status == OcrStatus.COMPLETED
    assert page.ocr_text == "hello from the page"
    assert page.s3_key == f"{base}.rm" and page.pdf_s3_key == f"{base}.pdf"
    notebook = db.query(Notebook).filter_by(notebook_uuid=NB_UUID).one()
    assert notebook.id == body["notebook_id"] and notebook.visible_name == "Real notebook"
    used = db.query(QuotaUsage).filter_by(user_id=user.id, quota_type=QuotaType.OCR).one().used
    assert used == 1


@pytest.mark.skipif(shutil.which("rsvg-convert") is None, reason="rsvg-convert not installed")
def test_real_rm_file_through_the_whole_converter(db, api):
    client, _, storage = api
    rm_bytes = (FIXTURES / "page_3.rm").read_bytes()
    ocr = MagicMock()
    ocr.extract_text_from_pdf = AsyncMock(return_value="text")

    with patch("app.api.processing.OCRService", return_value=ocr):
        resp = _upload_page(client, rm_bytes)

    assert resp.status_code == 200, resp.text
    sent_pdf = ocr.extract_text_from_pdf.await_args.args[0]
    assert sent_pdf.startswith(b"%PDF")
    assert any(k.endswith(".pdf") and v.startswith(b"%PDF") for k, v in storage.stored.items())


def test_unreadable_rm_file_stores_no_page_and_skips_ocr(db, api):
    """The real content check rejects garbage: no OCR, no quota use, no page row."""
    client, user, storage = api
    ocr = MagicMock()
    ocr.extract_text_from_pdf = AsyncMock(return_value="never")

    with patch("app.api.processing.OCRService", return_value=ocr):
        resp = _upload_page(client, (FIXTURES / "corrupted_page.rm").read_bytes())

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["page_count"] == 0 and body["page_id"] is None and body["extracted_text"] == ""
    ocr.extract_text_from_pdf.assert_not_awaited()
    db.expire_all()
    assert db.query(Page).count() == 0
    assert storage.stored == {}
    used = db.query(QuotaUsage).filter_by(user_id=user.id, quota_type=QuotaType.OCR).one().used
    assert used == 0


def test_same_real_rm_file_twice_is_not_ocrd_again(db, api):
    client, _, _ = api
    rm_bytes = (FIXTURES / "page_3.rm").read_bytes()
    ocr = MagicMock()
    ocr.extract_text_from_pdf = AsyncMock(return_value="once")

    with patch.object(RMConverter, "svg_to_pdf_bytes", lambda self, svg: b"%PDF"), patch(
        "app.api.processing.OCRService", return_value=ocr
    ):
        first = _upload_page(client, rm_bytes)
        second = _upload_page(client, rm_bytes)

    assert first.status_code == second.status_code == 200
    assert first.json()["page_id"] == second.json()["page_id"]
    assert second.json()["extracted_text"] == "once"
    assert ocr.extract_text_from_pdf.await_count == 1
    assert db.query(Page).count() == 1


# ---------------------------------------------------------------------------
# POST /sync/metadata
# ---------------------------------------------------------------------------


def _meta(*notebooks):
    return {"notebooks": list(notebooks)}


def _nb(prefix, pages, **extra):
    return {
        "uuid": _uuid(prefix, 0),
        "visible_name": extra.pop("name", f"Notebook {prefix}"),
        "pages": pages,
        **extra,
    }


def _order(db, notebook_uuid):
    db.expire_all()
    nb = db.query(Notebook).filter_by(notebook_uuid=notebook_uuid).one()
    rows = (
        db.query(Page.page_uuid)
        .join(NotebookPage, NotebookPage.page_id == Page.id)
        .filter(NotebookPage.notebook_id == nb.id)
        .order_by(NotebookPage.page_number)
        .all()
    )
    return [r[0] for r in rows]


def test_metadata_sync_creates_notebooks_and_not_synced_stubs(db, api):
    client, user, _ = api
    pages = [_uuid(1, i) for i in range(1, 4)]

    resp = client.post(
        f"{API}/sync/metadata", json=_meta(_nb(1, pages, name="Journal", pinned=True))
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert (body["notebooks_created"], body["notebooks_updated"]) == (1, 0)
    assert (body["pages_registered"], body["pages_already_synced"], body["skipped"]) == (3, 0, 0)

    nb = db.query(Notebook).filter_by(notebook_uuid=_uuid(1, 0)).one()
    assert (nb.user_id, nb.visible_name, nb.pinned) == (user.id, "Journal", True)
    assert _order(db, nb.notebook_uuid) == pages
    statuses = {p.ocr_status for p in db.query(Page).filter_by(notebook_id=nb.id)}
    assert statuses == {OcrStatus.NOT_SYNCED}


def test_metadata_resync_reorders_and_drops_removed_pages(db, api):
    client, _, _ = api
    a, b, c = (_uuid(2, i) for i in (1, 2, 3))
    assert client.post(f"{API}/sync/metadata", json=_meta(_nb(2, [a, b, c]))).status_code == 200

    resp = client.post(f"{API}/sync/metadata", json=_meta(_nb(2, [c, a], name="Renamed")))

    assert resp.status_code == 200, resp.text
    assert (resp.json()["notebooks_created"], resp.json()["notebooks_updated"]) == (0, 1)
    assert _order(db, _uuid(2, 0)) == [c, a]
    assert db.query(Notebook).filter_by(notebook_uuid=_uuid(2, 0)).one().visible_name == "Renamed"


def test_metadata_sync_keeps_uploaded_pages_and_skips_bad_ids(db, api):
    client, user, _ = api
    done, new = _uuid(3, 1), _uuid(3, 2)
    assert client.post(f"{API}/sync/metadata", json=_meta(_nb(3, [done]))).status_code == 200
    page = db.query(Page).filter_by(page_uuid=done).one()
    page.ocr_status, page.ocr_text, page.s3_key = OcrStatus.COMPLETED, "kept", "users/1/page.rm"
    db.commit()

    body = _meta(
        _nb(3, [done, new, "../not-a-uuid"]),
        {"uuid": "also-not-a-uuid", "visible_name": "Bad", "pages": []},
    )
    resp = client.post(f"{API}/sync/metadata", json=body)

    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["skipped"] == 2
    assert (out["pages_registered"], out["pages_already_synced"]) == (1, 1)
    db.expire_all()
    kept = db.query(Page).filter_by(page_uuid=done).one()
    assert (kept.ocr_status, kept.ocr_text) == (OcrStatus.COMPLETED, "kept")
    assert db.query(Notebook).filter_by(user_id=user.id).count() == 1
    assert _order(db, _uuid(3, 0)) == [done, new]


def test_metadata_sync_rejects_malformed_body(api):
    client, _, _ = api
    assert client.post(f"{API}/sync/metadata", json={"notebooks": [{"pages": []}]}).status_code == 422
    assert client.post(f"{API}/sync/metadata", json={}).status_code == 422


# ---------------------------------------------------------------------------
# GET /notebooks/tree
# ---------------------------------------------------------------------------


def _find(nodes, notebook_uuid):
    for node in nodes:
        if node["notebook_uuid"] == notebook_uuid:
            return node
        found = _find(node["children"], notebook_uuid)
        if found:
            return found
    return None


def test_tree_shows_folder_nesting_and_progress_after_metadata_sync_and_upload(db, api):
    client, _, _ = api
    folder = {"uuid": _uuid(4, 0), "visible_name": "Work", "document_type": "folder", "pages": []}
    pages = [_uuid(5, 1), _uuid(5, 2)]
    notebook = _nb(5, pages, name="Meeting notes", parent_uuid=_uuid(4, 0))
    assert client.post(f"{API}/sync/metadata", json=_meta(folder, notebook)).status_code == 200

    tree = client.get(f"{API}/notebooks/tree")
    assert tree.status_code == 200, tree.text
    assert tree.json()["total"] == 2
    root = tree.json()["tree"]
    assert [n["visible_name"] for n in root] == ["Work"] and root[0]["is_folder"] is True
    child = _find(root, _uuid(5, 0))
    assert child["visible_name"] == "Meeting notes" and child["preview"] is None
    assert child["sync_progress"] == {
        "total_pages": 2, "synced_pages": 0, "not_synced_pages": 2, "pending_quota_pages": 0,
    }

    # One page is uploaded and OCR'd: progress and preview follow.
    page = db.query(Page).filter_by(page_uuid=pages[1]).one()
    page.ocr_status, page.ocr_text = OcrStatus.COMPLETED, "Agenda for Monday"
    db.commit()
    child = _find(client.get(f"{API}/notebooks/tree").json()["tree"], _uuid(5, 0))
    assert child["sync_progress"]["synced_pages"] == 1
    assert child["sync_progress"]["not_synced_pages"] == 1
    assert child["preview"] == "Agenda for Monday"


def test_tree_only_lists_the_callers_notebooks(db, api):
    client, _, _ = api
    other = User(email="other-tree@example.com", clerk_user_id="clerk_other_tree")
    db.add(other)
    db.commit()
    db.add(Notebook(user_id=other.id, notebook_uuid=str(uuid.uuid4()), visible_name="Not mine", document_type="notebook"))
    db.commit()

    body = client.get(f"{API}/notebooks/tree").json()

    assert body == {"tree": [], "total": 0}


def test_tree_and_metadata_require_authentication(db, test_app, reset_rate_limiter):  # noqa: F811
    with TestClient(test_app) as client:
        assert client.get(f"{API}/notebooks/tree").status_code in (401, 403)
        assert client.post(f"{API}/sync/metadata", json=_meta()).status_code in (401, 403)


# ---------------------------------------------------------------------------
# /waitlist invite and admin flow
# ---------------------------------------------------------------------------


@pytest.fixture
def waitlist(db, api, monkeypatch):
    client, user, _ = api
    monkeypatch.setattr(get_settings(), "admin_user_ids", "clerk_risky")
    service = MagicMock()
    with patch("app.utils.email.get_email_service", return_value=service):
        yield client, db, service


def _entry(db, email, status="pending"):
    entry = WaitlistEntry(email=email, name=email.split("@")[0], status=status)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def test_approve_sends_invite_and_the_invite_then_validates(waitlist):
    client, db, service = waitlist
    entry = _entry(db, "invitee@example.com")

    resp = client.post(f"{API}/waitlist/admin/{entry.id}/approve")

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved" and resp.json()["approved_at"]
    db.expire_all()
    token = db.get(WaitlistEntry, entry.id).invite_token
    assert token
    kwargs = service.send_invite_approved_email.call_args.kwargs
    assert kwargs["email"] == "invitee@example.com"
    assert kwargs["invite_link"].endswith(f"/sign-up?invite={token}")

    valid = client.get(f"{API}/waitlist/validate-invite", params={"token": token})
    assert valid.json() == {"valid": True, "email": "invitee@example.com", "reason": None}


def test_validate_invite_rejects_garbage_unapproved_and_claimed(waitlist):
    client, db, _ = waitlist
    garbage = client.get(f"{API}/waitlist/validate-invite", params={"token": "nope"})
    assert garbage.json()["valid"] is False

    pending = _entry(db, "pending@example.com")
    unapproved = client.get(
        f"{API}/waitlist/validate-invite",
        params={"token": _create_invite_token(pending.email, pending.id)},
    )
    assert unapproved.json() == {"valid": False, "email": None, "reason": "Invite is not valid"}

    claimed = _entry(db, "claimed@example.com", status="claimed")
    used = client.get(
        f"{API}/waitlist/validate-invite",
        params={"token": _create_invite_token(claimed.email, claimed.id)},
    )
    assert used.json()["valid"] is False and "already been used" in used.json()["reason"]


def test_approve_twice_and_unknown_entry(waitlist):
    client, db, service = waitlist
    entry = _entry(db, "twice@example.com")
    assert client.post(f"{API}/waitlist/admin/{entry.id}/approve").status_code == 200

    assert client.post(f"{API}/waitlist/admin/{entry.id}/approve").status_code == 400
    assert client.post(f"{API}/waitlist/admin/99999/approve").status_code == 404
    assert service.send_invite_approved_email.call_count == 1


def test_admin_list_filters_and_counts(waitlist):
    client, db, _ = waitlist
    _entry(db, "p1@example.com")
    _entry(db, "p2@example.com")
    _entry(db, "a1@example.com", status="approved")

    body = client.get(f"{API}/waitlist/admin").json()
    assert body["total"] == 3
    assert body["stats"] == {"pending": 2, "approved": 1, "claimed": 0}

    approved = client.get(f"{API}/waitlist/admin", params={"status": "approved"}).json()
    assert approved["total"] == 1 and approved["entries"][0]["email"] == "a1@example.com"


def test_bulk_approve_reports_each_entry(waitlist):
    client, db, service = waitlist
    ok = _entry(db, "bulk-ok@example.com")
    done = _entry(db, "bulk-done@example.com", status="approved")

    resp = client.post(f"{API}/waitlist/admin/approve-bulk", json={"ids": [ok.id, done.id, 99999]})

    assert resp.status_code == 200, resp.text
    db.expire_all()
    assert db.get(WaitlistEntry, ok.id).status == "approved"
    assert service.send_invite_approved_email.call_count == 1
    assert "Not found" in resp.text and "Already approved" in resp.text


def test_waitlist_admin_endpoints_refuse_non_admins(db, api, monkeypatch):
    client, _, _ = api
    monkeypatch.setattr(get_settings(), "admin_user_ids", "someone_else")
    entry = _entry(db, "guarded@example.com")

    assert client.get(f"{API}/waitlist/admin").status_code == 403
    assert client.post(f"{API}/waitlist/admin/{entry.id}/approve").status_code == 403
    assert client.post(f"{API}/waitlist/admin/approve-bulk", json={"ids": [entry.id]}).status_code == 403
    db.expire_all()
    assert db.get(WaitlistEntry, entry.id).status == "pending"
