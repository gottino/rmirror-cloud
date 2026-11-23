"""
Headless mode (``--headless``, docs/local-api.md "Process contract").

In-process tests for the pieces, plus end-to-end runs of ``python -m app.main
--headless`` in a subprocess with a temp HOME, a temp config, a free port and a
null keyring (never the real keychain or ~/.config/rmirror).
"""

import os
import select
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app import main
from app.agent_loop import AgentLoop
from app.main import Agent, read_app_token, watch_parent_stdin

AGENT_DIR = Path(__file__).resolve().parents[2]
TOKEN = "f" * 64


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ----------------------------------------------------------------------
# In-process
# ----------------------------------------------------------------------


class TestAppToken:
    @pytest.mark.parametrize("value, ok", [(None, False), ("", False), ("x" * 31, False), ("x" * 32, True)])
    def test_read_app_token(self, value, ok):
        env = {} if value is None else {"RMIRROR_APP_TOKEN": value}
        assert (read_app_token(env) is not None) is ok

    def test_run_headless_without_token_exits_4(self, monkeypatch):
        monkeypatch.delenv("RMIRROR_APP_TOKEN", raising=False)
        with patch.object(main, "setup_logging") as setup:
            assert main.run_headless(None, False) == 4
        setup.assert_not_called()


@pytest.fixture
def open_stdin():
    """A pipe whose write end stays open (the parent app is alive)."""
    read_fd, write_fd = os.pipe()
    with os.fdopen(read_fd, "rb") as reader:
        yield reader
    os.close(write_fd)


class TestPortInUse:
    @pytest.mark.parametrize("family, host", [(socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")])
    def test_exit_3(self, monkeypatch, tmp_path, mock_keychain, open_stdin, family, host):
        port = free_port()
        config_file = tmp_path / "config.yaml"
        config_file.write_text(f"web:\n  port: {port}\nremarkable:\n  source_directory: {tmp_path}\n")
        monkeypatch.setenv("RMIRROR_APP_TOKEN", TOKEN)
        with socket.socket(family) as taken:
            if family == socket.AF_INET6:
                taken.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            taken.bind((host, port))
            taken.listen(1)
            with patch.object(main, "setup_logging"):
                assert main.run_headless(config_file, False, stdin=open_stdin) == 3

    def test_token_is_removed_from_the_environment(self, monkeypatch, tmp_path, open_stdin):
        monkeypatch.setenv("RMIRROR_APP_TOKEN", "short")
        assert main.run_headless(None, False, stdin=open_stdin) == 4
        assert "RMIRROR_APP_TOKEN" not in os.environ


class TestParentAlreadyGone:
    def test_none_or_closed(self):
        assert main.parent_already_gone(None)
        closed = MagicMock(closed=True)
        assert main.parent_already_gone(closed)

    def test_closed_pipe(self):
        read_fd, write_fd = os.pipe()
        os.close(write_fd)
        with os.fdopen(read_fd, "rb") as reader:
            assert main.parent_already_gone(reader)

    def test_open_pipe(self, open_stdin):
        assert not main.parent_already_gone(open_stdin)

    def test_headless_exits_0_without_starting(self, monkeypatch):
        monkeypatch.setenv("RMIRROR_APP_TOKEN", TOKEN)
        read_fd, write_fd = os.pipe()
        os.close(write_fd)
        with os.fdopen(read_fd, "rb") as reader, patch.object(main, "setup_logging") as setup:
            assert main.run_headless(None, False, stdin=reader) == 0
        setup.assert_not_called()


class TestParentWatch:
    def test_eof_calls_back(self):
        read_fd, write_fd = os.pipe()
        called = threading.Event()
        with os.fdopen(read_fd, "rb") as reader:
            thread = watch_parent_stdin(called.set, stream=reader)
            assert thread.daemon
            os.write(write_fd, b"ignored")
            assert not called.wait(0.2)
            os.close(write_fd)
            assert called.wait(5)


class TestHeadlessAgent:
    def test_bind_creates_server_with_app_token(self, test_config):
        test_config.web.port = free_port()
        agent = Agent(test_config, headless=True, app_token=TOKEN, agent_loop=AgentLoop())
        try:
            assert agent.bind_web_server() == test_config.web.port
            app = agent._web_server.app
            assert app.config["APP_TOKEN"] == TOKEN and app.config["HEADLESS"] is True
            # The port is taken now
            with socket.socket() as other, pytest.raises(OSError):
                other.bind(("127.0.0.1", test_config.web.port))
        finally:
            agent._web_server.server_close()

    def test_upload_batch_marks_quota_stale(self, test_config):
        agent = Agent(test_config, headless=True, agent_loop=AgentLoop())
        agent.quota_cache.note_attempt()
        agent._on_upload_batch({"uploaded": 0})
        assert not agent.quota_cache.refresh_due()
        agent._on_upload_batch({"uploaded": 2})
        assert agent.quota_cache.refresh_due()

    async def test_refresh_account_fills_cache_and_email(self, test_config):
        agent = Agent(test_config, headless=True, agent_loop=AgentLoop())
        cloud_sync = MagicMock(authenticated=True, user_email=None)
        cloud_sync.get_quota_status = AsyncMock(return_value={"used": 1, "limit": 30})
        cloud_sync.get_user_info = AsyncMock(return_value={"email": "a@b"})
        agent.cloud_sync = cloud_sync
        await agent.refresh_account()
        assert agent.quota_cache.snapshot()["remaining"] == 29
        cloud_sync.get_user_info.assert_awaited_once()

    async def test_refresh_account_never_raises(self, test_config):
        agent = Agent(test_config, headless=True, agent_loop=AgentLoop())
        cloud_sync = MagicMock(authenticated=True, user_email="a@b")
        cloud_sync.get_quota_status = AsyncMock(side_effect=RuntimeError("down"))
        agent.cloud_sync = cloud_sync
        await agent.refresh_account()
        assert agent.quota_cache.snapshot() is None


@pytest.mark.skipif(os.geteuid() == 0, reason="root can list any folder")
class TestUnreadableFolder:
    def test_watcher_is_not_started_until_readable(self, test_config, tmp_path):
        folder = tmp_path / "desktop"
        folder.mkdir()
        test_config.remarkable.source_directory = str(folder)
        test_config.remarkable.watch_enabled = True
        agent = Agent(test_config, agent_loop=AgentLoop())
        agent.cloud_sync = MagicMock(authenticated=True)
        os.chmod(folder, 0)
        try:
            assert agent.start_file_watcher_sync() is False
            assert agent.remarkable_folder_unreadable is True
            assert agent.remarkable_folder_missing is False
            assert agent._can_watch() is False
            assert agent.update_folder_flags() == "unreadable"
        finally:
            os.chmod(folder, 0o755)
        assert agent.update_folder_flags() == "ok"
        assert agent._can_watch() is True

    async def test_file_watcher_refuses_unreadable_folder(self, test_config, tmp_path):
        from app.watcher.file_watcher import FileWatcher

        folder = tmp_path / "desktop"
        folder.mkdir()
        test_config.remarkable.source_directory = str(folder)
        watcher = FileWatcher(test_config, MagicMock(), manifest=MagicMock())
        os.chmod(folder, 0)
        try:
            with pytest.raises(PermissionError):
                await watcher.start()
        finally:
            os.chmod(folder, 0o755)
        watcher.sync_queue.manifest.mark_initialised.assert_not_called()
        await watcher.sync_queue.stop()


# ----------------------------------------------------------------------
# End to end: the real process
# ----------------------------------------------------------------------


@pytest.fixture
def headless_env(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    fake_modules = tmp_path / "fake_modules"
    fake_modules.mkdir()
    # Headless mode must never import rumps: importing it fails the run
    (fake_modules / "rumps.py").write_text("raise ImportError('rumps must not be imported in headless mode')\n")
    source = tmp_path / "desktop"
    source.mkdir()
    port = free_port()
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "api:\n  url: http://127.0.0.1:9/api/v1\n"
        f"remarkable:\n  source_directory: {source}\n"
        f"web:\n  port: {port}\n  auto_launch_browser: true\n"
    )
    env = {
        **os.environ,
        "HOME": str(home),
        "RMIRROR_CONFIG_PATH": str(config_file),
        "RMIRROR_APP_TOKEN": TOKEN,
        "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring",
        "PYTHONPATH": os.pathsep.join([str(fake_modules), str(AGENT_DIR)]),
        "PYTHONUNBUFFERED": "1",
    }
    return {"env": env, "port": port, "home": home, "config": config_file}


def _spawn(headless_env, **env_overrides):
    env = {**headless_env["env"], **env_overrides}
    env = {k: v for k, v in env.items() if v is not None}
    return subprocess.Popen(
        [sys.executable, "-m", "app.main", "--headless"],
        cwd=AGENT_DIR,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _wait_ready(proc, timeout=30.0) -> str:
    """Read stdout (unbuffered, so select() sees every byte) until the ready line."""
    fd = proc.stdout.fileno()
    deadline = time.monotonic() + timeout
    data = b""
    while time.monotonic() < deadline:
        ready, _, _ = select.select([fd], [], [], 0.2)
        if not ready:
            continue
        chunk = os.read(fd, 65536)
        if not chunk:
            break
        data += chunk
        for line in data.decode(errors="replace").splitlines():
            if line.startswith("RMIRROR_CORE_READY"):
                return line.strip()
    proc.kill()
    raise AssertionError(f"no ready line; stdout: {data!r}; stderr: {proc.stderr.read().decode()}")


class TestHeadlessProcess:
    def test_ready_token_and_stdin_eof(self, headless_env):
        proc = _spawn(headless_env)
        try:
            port = headless_env["port"]
            assert _wait_ready(proc) == f"RMIRROR_CORE_READY port={port} api=2"
            base = f"http://127.0.0.1:{port}"
            assert httpx.get(f"{base}/health").status_code == 200
            assert httpx.get(f"{base}/api/v2/state").status_code == 401
            resp = httpx.get(f"{base}/api/v2/state", headers={"X-RMirror-App-Token": TOKEN})
            assert resp.status_code == 200
            assert resp.json()["auth"]["signed_in"] is False
            assert resp.json()["auth"]["state"] == "signed_out"
            # Legacy routes do not exist in headless mode
            assert httpx.get(f"{base}/api/status").status_code == 404
            assert httpx.post(f"{base}/api/config", json={"api": {"url": "http://x"}}).status_code == 404
            # Served on [::1] too
            v6 = httpx.get(f"http://[::1]:{port}/api/v2/state", headers={"X-RMirror-App-Token": TOKEN})
            assert v6.status_code == 200
            started = time.monotonic()
            proc.stdin.close()
            assert proc.wait(timeout=10) == 0
            assert time.monotonic() - started < 5
            # Nothing on stdout after the ready line
            assert proc.stdout.read() == b""
        finally:
            if proc.poll() is None:
                proc.kill()
        # Only the temp HOME was written (log file), never a config next to it
        assert (headless_env["home"] / ".config/rmirror/agent.log").exists()
        assert not (headless_env["home"] / ".config/rmirror/config.yaml").exists()

    def test_sigterm_exits_0(self, headless_env):
        proc = _spawn(headless_env)
        try:
            _wait_ready(proc)
            proc.send_signal(signal.SIGTERM)
            assert proc.wait(timeout=10) == 0
        finally:
            if proc.poll() is None:
                proc.kill()

    def test_closed_stdin_exits_0_without_starting(self, headless_env):
        env = {**headless_env["env"]}
        proc = subprocess.Popen(
            [sys.executable, "-m", "app.main", "--headless"], cwd=AGENT_DIR, env=env,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        assert proc.wait(timeout=30) == 0
        assert b"RMIRROR_CORE_READY" not in proc.stdout.read()

    def test_missing_token_exits_4(self, headless_env):
        proc = _spawn(headless_env, RMIRROR_APP_TOKEN=None)
        assert proc.wait(timeout=30) == 4
        assert b"RMIRROR_CORE_READY" not in proc.stdout.read()

    @pytest.mark.parametrize("family, host", [(socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")])
    def test_port_in_use_exits_3(self, headless_env, family, host):
        with socket.socket(family) as taken:
            if family == socket.AF_INET6:
                taken.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            taken.bind((host, headless_env["port"]))
            taken.listen(1)
            proc = _spawn(headless_env)
            assert proc.wait(timeout=30) == 3
            assert b"RMIRROR_CORE_READY" not in proc.stdout.read()
