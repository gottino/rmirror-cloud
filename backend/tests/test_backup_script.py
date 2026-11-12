"""Dry-run tests for scripts/backup-db.sh using a fake pg_dump on PATH."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "backup-db.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash not available")

FAKE_PG_DUMP = """#!/bin/bash
case "$FAKE_PG_DUMP_MODE" in
  ok) head -c 4096 /dev/zero | tr '\\0' 'x' ;;
  empty) exit 0 ;;
  fail) echo "boom" >&2; exit 3 ;;
esac
"""


def run_script(tmp_path, mode, extra_env=None, with_aws=False):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "pg_dump"
    fake.write_text(FAKE_PG_DUMP)
    fake.chmod(0o755)
    if with_aws:
        aws = bin_dir / "aws"
        aws.write_text('#!/bin/bash\necho "$@" >> "$AWS_LOG"\n')
        aws.chmod(0o755)
    out = tmp_path / "out"
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FAKE_PG_DUMP_MODE": mode,
        "BACKUP_DB_NAME": "testdb",
        "BACKUP_DIR": str(out),
        "AWS_LOG": str(tmp_path / "aws.log"),
    }
    env.update(extra_env or {})
    result = subprocess.run(
        [BASH, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30
    )
    return result, out


def dumps(out):
    return sorted(out.glob("testdb_*.dump")) if out.exists() else []


def test_successful_dump_is_kept(tmp_path):
    result, out = run_script(tmp_path, "ok")
    assert result.returncode == 0, result.stderr
    assert len(dumps(out)) == 1
    assert dumps(out)[0].stat().st_size == 4096
    assert not list(out.glob("*.partial"))


def test_failing_pg_dump_exits_nonzero_and_leaves_nothing(tmp_path):
    result, out = run_script(tmp_path, "fail")
    assert result.returncode != 0
    assert dumps(out) == []
    assert not list(out.glob("*.partial"))


def test_empty_dump_exits_nonzero_and_leaves_nothing(tmp_path):
    result, out = run_script(tmp_path, "empty")
    assert result.returncode != 0
    assert "empty or too small" in result.stderr
    assert dumps(out) == []


def test_keeps_only_newest_seven(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    for i in range(10):
        f = out / f"testdb_2020010{i % 10}_000000.dump"
        f.write_bytes(b"x" * 2048)
        os.utime(f, (1_600_000_000 + i, 1_600_000_000 + i))
    result, out = run_script(tmp_path, "ok")
    assert result.returncode == 0, result.stderr
    assert len(dumps(out)) == 7


def test_upload_configured_without_cli_fails(tmp_path):
    s3 = {
        "BACKUP_S3_BUCKET": "b",
        "BACKUP_S3_ENDPOINT": "https://s3.example.invalid",
        "BACKUP_S3_ACCESS_KEY": "ak-secret-value",
        "BACKUP_S3_SECRET_KEY": "sk-secret-value",
        # Minimal PATH without aws; fake pg_dump dir is added by run_script.
    }
    result, _ = run_script(tmp_path, "ok", s3)
    if shutil.which("aws"):
        pytest.skip("a real aws CLI is installed on this machine")
    assert result.returncode != 0
    assert "aws" in result.stderr
    assert "secret-value" not in result.stdout + result.stderr


def test_upload_uses_endpoint_and_does_not_print_secrets(tmp_path):
    s3 = {
        "BACKUP_S3_BUCKET": "bucket-x",
        "BACKUP_S3_ENDPOINT": "https://s3.example.invalid",
        "BACKUP_S3_ACCESS_KEY": "ak-secret-value",
        "BACKUP_S3_SECRET_KEY": "sk-secret-value",
    }
    result, _ = run_script(tmp_path, "ok", s3, with_aws=True)
    assert result.returncode == 0, result.stderr
    log = (tmp_path / "aws.log").read_text()
    assert "--endpoint-url https://s3.example.invalid" in log
    assert "s3://bucket-x/testdb_" in log
    assert "secret-value" not in result.stdout + result.stderr + log


def test_partial_s3_config_fails(tmp_path):
    result, _ = run_script(tmp_path, "ok", {"BACKUP_S3_BUCKET": "b"})
    assert result.returncode != 0
    assert dumps(tmp_path / "out") == []
