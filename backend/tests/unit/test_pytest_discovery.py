"""Guard the default test command.

Running ``pytest`` from the backend root with no arguments must collect the
real suite cleanly. Without a ``testpaths`` setting, pytest also discovers the
root-level ``test_*.py`` live-integration scripts, one of which makes a live
Notion API call at import time and aborts collection — breaking the obvious
``poetry run pytest`` command for every contributor and CI.

This test runs collection in a subprocess so it reflects exactly what a bare
``pytest`` invocation does.
"""

import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_default_pytest_collection_succeeds():
    """`pytest --collect-only` from the backend root must exit cleanly (rc 0)."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )

    assert result.returncode == 0, (
        "Default pytest collection failed — discovery is picking up scripts that "
        "error on import (likely root-level live test_*.py). "
        f"rc={result.returncode}\n--- stdout ---\n{result.stdout[-2000:]}\n"
        f"--- stderr ---\n{result.stderr[-2000:]}"
    )


def test_collection_only_includes_the_tests_directory():
    """Every collected item must live under tests/.

    The root-level live scripts (backend/test_*.py) would appear as node ids
    without a ``tests/`` prefix; legitimate suite files (e.g.
    ``tests/unit/test_notion_sync.py``) always carry it. Asserting the prefix is
    robust against name collisions between a root script and a real test file.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )

    node_lines = [line for line in result.stdout.splitlines() if "::" in line]
    assert node_lines, "expected to collect at least some tests"

    offenders = [line for line in node_lines if not line.startswith("tests/")]
    assert not offenders, (
        "collected items outside the tests/ directory (root-level scripts leaking "
        f"into discovery): {offenders[:5]}"
    )
