"""
Pieces behind the local API v2 that are not routes: the first-run choice, the
folder state, the document scan, the quota cache, the manifest summaries and
the sync queue / initial sync signals.
"""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.remarkable.library import DocumentInfo, folder_state, scan_documents, scan_library
from app.sync.cloud_sync import AuthenticationRequiredError, QuotaExceededError, RateLimitError
from app.sync.first_run import choose_notebooks, suggest_first_sync
from app.sync.initial_sync import InitialSync
from app.sync.manifest import UploadManifest, fingerprint_file
from app.sync.queue import WAITING_OFFLINE, WAITING_RATE_LIMITED, SyncQueue
from app.sync.quota_cache import QuotaCache, iso_utc

BASE = datetime(2026, 11, 1, tzinfo=UTC)


def doc(uuid: str, pages: int, days_ago_opened: int | None = None, days_ago_modified: int = 100) -> DocumentInfo:
    return DocumentInfo(
        uuid=uuid,
        name=uuid.title(),
        page_count=pages,
        last_opened_at=None if days_ago_opened is None else BASE - timedelta(days=days_ago_opened),
        last_modified_at=BASE - timedelta(days=days_ago_modified),
    )


# ----------------------------------------------------------------------
# First-run choice (pure)
# ----------------------------------------------------------------------


class TestChooseNotebooks:
    def test_most_recent_first(self):
        docs = [doc("old", 1, 30), doc("new", 1, 1), doc("mid", 1, 10)]
        assert [d.uuid for d in choose_notebooks(docs, None, 3)] == ["new", "mid", "old"]

    def test_falls_back_to_last_modified(self):
        docs = [doc("opened", 1, days_ago_opened=20), doc("modified-only", 1, None, days_ago_modified=2)]
        assert [d.uuid for d in choose_notebooks(docs, None, 2)] == ["modified-only", "opened"]

    def test_never_exceeds_remaining(self):
        docs = [doc(f"nb{i}", pages, i) for i, pages in enumerate([7, 5, 3, 9, 1, 4])]
        for remaining in range(0, 30):
            for max_count in range(1, 7):
                chosen = choose_notebooks(docs, remaining, max_count)
                assert sum(d.page_count for d in chosen) <= remaining
                assert len(chosen) <= max_count

    def test_skips_one_that_does_not_fit_and_tries_the_next(self):
        docs = [doc("big", 50, 1), doc("small", 5, 2), doc("medium", 8, 3), doc("tiny", 1, 4)]
        assert [d.uuid for d in choose_notebooks(docs, 10, 3)] == ["small", "tiny"]

    def test_unlimited_takes_max(self):
        docs = [doc(f"nb{i}", 1000, i) for i in range(5)]
        assert [d.uuid for d in choose_notebooks(docs, None, 3)] == ["nb0", "nb1", "nb2"]

    def test_empty_pages_are_not_suggested(self):
        assert choose_notebooks([doc("empty", 0, 1)], None, 3) == []

    def test_no_notebooks(self):
        assert choose_notebooks([], 100, 3) == []


class TestSuggestFirstSync:
    def test_signed_out(self):
        s = suggest_first_sync(signed_in=False, folder_ok=True, documents=[doc("a", 1, 1)], remaining=10, max_count=3)
        assert (s.reason, s.notebooks) == ("not_signed_in", [])

    def test_folder_unavailable(self):
        s = suggest_first_sync(signed_in=True, folder_ok=False, documents=[], remaining=10, max_count=3)
        assert s.reason == "folder_unavailable"

    def test_no_notebooks(self):
        s = suggest_first_sync(signed_in=True, folder_ok=True, documents=[doc("e", 0, 1)], remaining=10, max_count=3)
        assert (s.reason, s.notebooks) == ("no_notebooks", [])

    def test_quota_exhausted(self):
        s = suggest_first_sync(signed_in=True, folder_ok=True, documents=[doc("a", 1, 1)], remaining=0, max_count=3)
        assert (s.reason, s.notebooks) == ("quota_exhausted", [])

    def test_ok_with_total(self):
        s = suggest_first_sync(
            signed_in=True, folder_ok=True, documents=[doc("a", 4, 1), doc("b", 6, 2)], remaining=None, max_count=3
        )
        assert s.reason == "ok" and s.total_pages == 10


# ----------------------------------------------------------------------
# Folder state and document scan
# ----------------------------------------------------------------------


class TestFolderState:
    def test_ok(self, tmp_path):
        assert folder_state(tmp_path) == "ok"

    def test_missing(self, tmp_path):
        assert folder_state(tmp_path / "nope") == "missing"

    def test_file_is_missing(self, tmp_path):
        f = tmp_path / "file"
        f.write_text("x")
        assert folder_state(f) == "missing"

    @pytest.mark.skipif(os.geteuid() == 0, reason="root can list any folder")
    def test_unreadable(self, tmp_path):
        d = tmp_path / "locked"
        d.mkdir()
        os.chmod(d, 0)
        try:
            assert folder_state(d) == "unreadable"
        finally:
            os.chmod(d, 0o755)

    @pytest.mark.parametrize("error", [PermissionError(1, "Operation not permitted"), OSError(13, "denied")])
    def test_permission_errors_are_unreadable(self, tmp_path, monkeypatch, error):
        def scandir(path):
            raise error

        monkeypatch.setattr("app.remarkable.library.os.scandir", scandir)
        assert folder_state(tmp_path) == "unreadable"


def _meta(root: Path, uuid: str, **data) -> None:
    (root / f"{uuid}.metadata").write_text(json.dumps(data))


class TestScanDocuments:
    def test_folders_trash_and_page_counts(self, tmp_path):
        _meta(tmp_path, "f1", visibleName="Work", type="CollectionType", parent="")
        _meta(tmp_path, "f2", visibleName="Sub", type="CollectionType", parent="f1")
        _meta(tmp_path, "tf", visibleName="Trashed folder", type="CollectionType", parent="trash")
        _meta(tmp_path, "a", visibleName="A", type="DocumentType", parent="f2", lastOpened="1700000000000")
        _meta(tmp_path, "b", visibleName="B", type="DocumentType", parent="tf")
        _meta(tmp_path, "c", visibleName="C", type="DocumentType", parent="", deleted=True)
        _meta(tmp_path, "d", visibleName="D", type="DocumentType", parent="", lastOpened="0", lastModified="1700000000000")
        _meta(tmp_path, "t", visibleName="T", type="TemplateType")
        (tmp_path / "a.content").write_text(json.dumps({"pageCount": 4}))
        (tmp_path / "d.content").write_text(json.dumps({"cPages": {"pages": [
            {"id": "1"}, {"id": "2", "deleted": {"value": 1}}, {"id": "3"}]}}))
        (tmp_path / "broken.metadata").write_text("{not json")

        docs = {d.uuid: d for d in scan_documents(tmp_path)}
        assert set(docs) == {"a", "d"}
        assert docs["a"].folder_path == ["Work", "Sub"]
        assert docs["a"].page_count == 4
        assert docs["a"].last_opened_at is not None
        assert docs["d"].page_count == 2
        assert docs["d"].last_opened_at is None
        assert docs["d"].recency == docs["d"].last_modified_at

    def test_parent_cycle_does_not_hang(self, tmp_path):
        _meta(tmp_path, "x", visibleName="X", type="CollectionType", parent="y")
        _meta(tmp_path, "y", visibleName="Y", type="CollectionType", parent="x")
        _meta(tmp_path, "n", visibleName="N", type="DocumentType", parent="x")
        (doc_,) = scan_documents(tmp_path)
        assert doc_.folder_path == ["Y", "X"]


def _folder(root: Path, uuid: str, name: str | None, parent: str = "", **extra) -> None:
    data = {"type": "CollectionType", "parent": parent, **extra}
    if name is not None:
        data["visibleName"] = name
    _meta(root, uuid, **data)


class TestScanLibraryFolders:
    def test_nested_three_deep_and_empty_folder(self, tmp_path):
        _folder(tmp_path, "a", "A")
        _folder(tmp_path, "b", "B", "a")
        _folder(tmp_path, "c", "C", "b")
        _folder(tmp_path, "empty", "Empty")
        _meta(tmp_path, "n", visibleName="N", type="DocumentType", parent="c")
        lib = scan_library(tmp_path)
        assert [(f.uuid, f.name, f.parent_uuid) for f in lib.folders] == [
            ("a", "A", None), ("b", "B", "a"), ("c", "C", "b"), ("empty", "Empty", None)]
        (n,) = lib.documents
        assert n.parent_uuid == "c"
        assert n.folder_path == ["A", "B", "C"]

    def test_trashed_folder_and_everything_under_it_is_absent(self, tmp_path):
        _folder(tmp_path, "t", "T", "trash")
        _folder(tmp_path, "t2", "T2", "t")
        _folder(tmp_path, "d", "D", deleted=True)
        _folder(tmp_path, "d2", "D2", "d")
        _folder(tmp_path, "keep", "Keep")
        _meta(tmp_path, "n1", visibleName="N1", type="DocumentType", parent="t2")
        _meta(tmp_path, "n2", visibleName="N2", type="DocumentType", parent="d2")
        _meta(tmp_path, "n3", visibleName="N3", type="DocumentType", parent="trash")
        _meta(tmp_path, "n4", visibleName="N4", type="DocumentType", parent="keep")
        lib = scan_library(tmp_path)
        assert [f.uuid for f in lib.folders] == ["keep"]
        assert [d.uuid for d in lib.documents] == ["n4"]

    def test_missing_parent_becomes_top_level_notebooks_keep_it(self, tmp_path):
        _folder(tmp_path, "orphan", "Orphan", "ghost")
        _meta(tmp_path, "n", visibleName="N", type="DocumentType", parent="orphan")
        _meta(tmp_path, "m", visibleName="M", type="DocumentType", parent="ghost")
        lib = scan_library(tmp_path)
        assert [(f.uuid, f.parent_uuid) for f in lib.folders] == [("orphan", None)]
        docs = {d.uuid: d for d in lib.documents}
        assert docs["n"].parent_uuid == "orphan"
        assert docs["n"].folder_path == ["Orphan"]
        assert docs["m"].parent_uuid is None
        assert docs["m"].folder_path == []

    def test_parent_loop_terminates_both_top_level(self, tmp_path):
        _folder(tmp_path, "x", "X", "y")
        _folder(tmp_path, "y", "Y", "x")
        _folder(tmp_path, "z", "Z", "x")
        _meta(tmp_path, "n", visibleName="N", type="DocumentType", parent="x")
        lib = scan_library(tmp_path)
        assert {f.uuid: f.parent_uuid for f in lib.folders} == {"x": None, "y": None, "z": "x"}
        assert lib.documents[0].parent_uuid == "x"
        assert lib.documents[0].folder_path == ["Y", "X"]

    def test_self_parent_is_top_level(self, tmp_path):
        _folder(tmp_path, "s", "S", "s")
        assert [(f.uuid, f.parent_uuid) for f in scan_library(tmp_path).folders] == [("s", None)]

    def test_name_fallback_and_stable_order(self, tmp_path):
        _folder(tmp_path, "u2", None)
        _folder(tmp_path, "u1", "")
        _folder(tmp_path, "b", "beta")
        _folder(tmp_path, "a", "Alpha")
        _folder(tmp_path, "b2", "Beta")
        names = [(f.name, f.uuid) for f in scan_library(tmp_path).folders]
        assert names == [("Alpha", "a"), ("beta", "b"), ("Beta", "b2"), ("Untitled", "u1"), ("Untitled", "u2")]


# ----------------------------------------------------------------------
# Quota cache and timestamps
# ----------------------------------------------------------------------


class TestQuotaCache:
    def test_empty(self):
        assert QuotaCache().snapshot() is None

    def test_refresh_due(self):
        now = [0.0]
        cache = QuotaCache(clock=lambda: now[0])
        assert cache.refresh_due()
        cache.note_attempt()
        assert not cache.refresh_due()
        now[0] += QuotaCache.REFRESH_SECONDS - 1
        assert not cache.refresh_due()
        cache.mark_stale()
        assert cache.refresh_due()
        cache.note_attempt()
        now[0] += QuotaCache.REFRESH_SECONDS
        assert cache.refresh_due()

    def test_snapshot_and_clear(self):
        cache = QuotaCache()
        cache.store({"used": 250, "limit": 200, "reset_at": "2026-12-01T00:00:00"})
        snap = cache.snapshot()
        assert snap["remaining"] == 0
        assert snap["reset_at"] == "2026-12-01T00:00:00Z"
        cache.clear()
        assert cache.snapshot() is None

    def test_iso_utc(self):
        assert iso_utc(None) is None
        assert iso_utc("nonsense") is None
        assert iso_utc("2026-11-23T08:00:00+01:00") == "2026-11-23T07:00:00Z"
        assert iso_utc(datetime(2026, 11, 23, 8, tzinfo=UTC)) == "2026-11-23T08:00:00Z"
        assert iso_utc("2026-11-23T08:00:00", naive_is_utc=True) == "2026-11-23T08:00:00Z"


# ----------------------------------------------------------------------
# Manifest summaries
# ----------------------------------------------------------------------


class TestManifestSummaries:
    def test_last_upload_and_pages_per_notebook(self, tmp_path):
        source = tmp_path / "desktop"
        (source / "nb1").mkdir(parents=True)
        (source / "nb2").mkdir()
        files = []
        for name in ("nb1/a.rm", "nb1/b.rm", "nb2/c.rm", "nb1.metadata"):
            f = source / name
            f.write_bytes(name.encode())
            files.append(f)
        manifest = UploadManifest(tmp_path / "m.sqlite3", "host")
        assert manifest.last_upload_at() is None
        for f in files[:3]:
            manifest.record_upload(f, fingerprint_file(f))
        manifest.record_upload(files[3], fingerprint_file(files[3]))
        other = UploadManifest(tmp_path / "m.sqlite3", "other")
        other.record_upload(files[0], fingerprint_file(files[0]))
        assert manifest.last_upload_at() is not None
        assert manifest.uploaded_paths() == {str(f) for f in files}
        assert other.uploaded_paths() == {str(files[0])}

    def test_baseline_does_not_count(self, tmp_path):
        f = tmp_path / "nb" / "p.rm"
        f.parent.mkdir()
        f.write_bytes(b"x")
        manifest = UploadManifest(tmp_path / "m.sqlite3", "host")
        manifest.record_baseline(f, fingerprint_file(f))
        assert manifest.last_upload_at() is None
        assert manifest.uploaded_paths() == set()


# ----------------------------------------------------------------------
# Sync queue signals
# ----------------------------------------------------------------------


@pytest.fixture
def queue(test_config, tmp_path):
    cloud_sync = MagicMock()
    cloud_sync.authenticated = True
    cloud_sync.upload_file = AsyncMock(return_value={"success": True})
    seen = {}

    async def sleep(seconds):
        seen.setdefault("waiting", []).append(q.waiting_reason)

    test_config.sync.cooldown_seconds = 0
    q = SyncQueue(test_config, cloud_sync, manifest=UploadManifest(tmp_path / "m.sqlite3", "h"), sleep=sleep)
    q.metadata_sync = MagicMock()
    q.metadata_sync.run = AsyncMock(return_value={"success": True})
    q.seen = seen
    return q


def _page(tmp_path, name="p.rm"):
    f = tmp_path / "src" / "nb" / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(name.encode())
    return f


class TestQueueSignals:
    async def test_batch_callback(self, queue, tmp_path):
        batches = []
        queue.on_batch_complete = batches.append
        await queue.add(_page(tmp_path), "nb", "rm")
        await queue._run_once()
        assert batches and batches[0]["uploaded"] == 1

    async def test_batch_callback_errors_are_ignored(self, queue, tmp_path):
        queue.on_batch_complete = MagicMock(side_effect=RuntimeError("boom"))
        await queue.add(_page(tmp_path), "nb", "rm")
        assert (await queue._run_once())["uploaded"] == 1

    async def test_waiting_reason_while_rate_limited(self, queue, tmp_path):
        queue.cloud_sync.upload_file.side_effect = RateLimitError("slow", retry_after=3)
        await queue.add(_page(tmp_path), "nb", "rm")
        await queue._run_once()
        assert queue.seen["waiting"] == [WAITING_RATE_LIMITED]
        assert queue.waiting_reason is None

    async def test_waiting_reason_while_offline(self, queue, tmp_path):
        from app.sync.cloud_sync import CloudSyncError

        queue.cloud_sync.upload_file.side_effect = [CloudSyncError("down", transient=True), {"success": True}]
        await queue.add(_page(tmp_path), "nb", "rm")
        await queue._run_once()
        assert queue.seen["waiting"] == [WAITING_OFFLINE]
        assert queue.waiting_reason is None


# ----------------------------------------------------------------------
# Initial sync stop reasons (reported only; the flow is unchanged)
# ----------------------------------------------------------------------


@pytest.fixture
def initial_sync(test_config, temp_remarkable_dir, tmp_path):
    test_config.remarkable.source_directory = str(temp_remarkable_dir)
    sync = InitialSync(test_config, AsyncMock(), manifest=UploadManifest(tmp_path / "m.sqlite3", "h"))
    sync.metadata_sync.run = AsyncMock(return_value={"success": True})
    sync._sleep = AsyncMock()
    return sync


class TestInitialSyncStopReason:
    async def test_none_when_fine(self, initial_sync):
        initial_sync.cloud_sync.upload_file.return_value = {"success": True}
        assert (await initial_sync.run())["stopped_reason"] is None

    async def test_quota(self, initial_sync):
        initial_sync.cloud_sync.upload_file.side_effect = QuotaExceededError("quota")
        assert (await initial_sync.run())["stopped_reason"] == "quota"

    async def test_sign_in(self, initial_sync):
        initial_sync.cloud_sync.upload_file.side_effect = AuthenticationRequiredError("again", status_code=401)
        stats = await initial_sync.run()
        assert stats["stopped_reason"] == "sign_in"
        # Not failed: left for the rescan after the next sign-in (will_retry)
        assert stats["failed"] == 0
        assert stats["rate_limited"] == 2
        # One attempt, then it stops instead of failing every page
        assert initial_sync.cloud_sync.upload_file.await_count == 1
