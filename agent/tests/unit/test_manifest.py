"""
Tests for the persistent upload manifest.
"""

import os
import threading
from pathlib import Path
from unittest.mock import patch

from app.config import Config
from app.sync import manifest as manifest_module
from app.sync.manifest import UploadManifest, fingerprint_file


def make_manifest(tmp_path: Path, host: str = "api.example.test") -> UploadManifest:
    return UploadManifest(tmp_path / "state" / "manifest.sqlite3", host)


class TestUploadManifest:
    def test_new_file_is_changed_until_recorded(self, tmp_path):
        manifest = make_manifest(tmp_path)
        f = tmp_path / "page.rm"
        f.write_bytes(b"v1")

        fp = manifest.changed_fingerprint(f)
        assert fp is not None and fp.sha256 == fingerprint_file(f).sha256

        manifest.record_upload(f, fp)
        assert manifest.changed_fingerprint(f) is None
        entry = manifest.get(f)
        assert entry.uploaded_at is not None and not entry.is_baseline

    def test_changed_content_is_detected(self, tmp_path):
        manifest = make_manifest(tmp_path)
        f = tmp_path / "page.rm"
        f.write_bytes(b"v1")
        manifest.record_upload(f, fingerprint_file(f))

        f.write_bytes(b"version two")
        fp = manifest.changed_fingerprint(f)
        assert fp is not None and fp.size == len(b"version two")

    def test_unchanged_size_and_mtime_skip_hashing(self, tmp_path):
        manifest = make_manifest(tmp_path)
        f = tmp_path / "page.rm"
        f.write_bytes(b"v1")
        manifest.record_upload(f, fingerprint_file(f))

        with patch.object(manifest_module, "fingerprint_file", side_effect=AssertionError("hashed")):
            assert manifest.changed_fingerprint(f) is None

    def test_touched_file_with_same_content_is_unchanged(self, tmp_path):
        manifest = make_manifest(tmp_path)
        f = tmp_path / "page.rm"
        f.write_bytes(b"v1")
        manifest.record_upload(f, fingerprint_file(f))

        st = os.stat(f)
        os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
        assert manifest.changed_fingerprint(f) is None
        # The new mtime is remembered, so the next check needs no hash
        assert manifest.get(f).mtime_ns == os.stat(f).st_mtime_ns

    def test_entries_are_per_api_host(self, tmp_path):
        prod = make_manifest(tmp_path, "rmirror.example")
        staging = make_manifest(tmp_path, "staging.rmirror.example")
        f = tmp_path / "page.rm"
        f.write_bytes(b"v1")

        prod.record_upload(f, fingerprint_file(f))
        prod.mark_initialised()

        assert prod.changed_fingerprint(f) is None
        assert staging.changed_fingerprint(f) is not None
        assert prod.is_initialised() and not staging.is_initialised()

    def test_host_callable_follows_config(self, tmp_path, test_config):
        with patch.object(Config, "get_default_config_path", return_value=tmp_path / "cfg" / "config.yaml"):
            manifest = UploadManifest.for_config(test_config)
        assert manifest.db_path == tmp_path / "cfg" / manifest_module.MANIFEST_FILENAME
        assert manifest.api_host == "test-api.rmirror.io"
        test_config.api.url = "https://other.example/api/v1"
        assert manifest.api_host == "other.example"

    def test_baseline_does_not_overwrite_upload(self, tmp_path):
        manifest = make_manifest(tmp_path)
        f = tmp_path / "page.rm"
        f.write_bytes(b"v1")
        manifest.record_upload(f, fingerprint_file(f))

        f.write_bytes(b"v2")
        assert manifest.record_baseline(f, fingerprint_file(f)) is False
        assert manifest.get(f).uploaded_at is not None

        g = tmp_path / "other.rm"
        g.write_bytes(b"x")
        assert manifest.record_baseline(g, fingerprint_file(g)) is True
        assert manifest.get(g).is_baseline

    def test_concurrent_writes_from_threads(self, tmp_path):
        manifest = make_manifest(tmp_path)
        files = []
        for i in range(40):
            f = tmp_path / f"{i}.rm"
            f.write_bytes(str(i).encode())
            files.append(f)

        errors = []

        def worker(chunk):
            try:
                for f in chunk:
                    manifest.record_upload(f, fingerprint_file(f))
            except Exception as e:  # pragma: no cover - reported below
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(files[i::4],)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        assert all(manifest.changed_fingerprint(f) is None for f in files)
