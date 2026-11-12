"""Dry-run tests for scripts/deploy.sh.

deploy.sh runs in a throwaway git checkout with fake sudo, systemctl,
journalctl, poetry, curl, pg_dump and sleep on PATH. The fakes append to a
log file so the tests can assert the order of operations and which commit
was checked out at each step.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
DEPLOY = SCRIPTS / "deploy.sh"
SUDOERS = SCRIPTS / "setup-deploy-permissions.sh"
BASH = shutil.which("bash")
GIT = shutil.which("git")

pytestmark = pytest.mark.skipif(BASH is None or GIT is None, reason="bash and git required")

FAKES = {
    "sudo": r"""#!/bin/bash
echo "sudo $*" >> "$DEPLOY_LOG"
while [[ "$1" == -* ]]; do
  if [ "$1" = "-u" ]; then shift 2; else shift; fi
done
exec "$@"
""",
    "systemctl": r"""#!/bin/bash
echo "systemctl $* @ $(git -C "$DEPLOY_APP_DIR" rev-parse HEAD)" >> "$DEPLOY_LOG"
""",
    "journalctl": r"""#!/bin/bash
echo "journalctl $*" >> "$DEPLOY_LOG"
""",
    "pg_dump": r"""#!/bin/bash
echo "pg_dump $*" >> "$DEPLOY_LOG"
head -c 4096 /dev/urandom
""",
    "poetry": r"""#!/bin/bash
head=$(git rev-parse HEAD)
case "$*" in
  "run python -")
    first=$(head -n 1)
    cat > /dev/null
    echo "config-check-current-code script=[$first] @ $head" >> "$DEPLOY_LOG"
    [ -z "$FAKE_CONFIG_FAIL" ] || { echo "Config check FAILED: missing settings: SECRET_KEY"; exit 1; }
    ;;
  "run python scripts/check_config.py")
    echo "config-check-new-code @ $head" >> "$DEPLOY_LOG"
    ;;
  "run alembic upgrade head")
    echo "migrate @ $head" >> "$DEPLOY_LOG"
    [ -z "$FAKE_MIGRATE_FAIL" ] || exit 1
    ;;
  install*)
    echo "install @ $head" >> "$DEPLOY_LOG"
    ;;
  *)
    echo "unexpected poetry $*" >> "$DEPLOY_LOG"; exit 99 ;;
esac
""",
    "curl": r"""#!/bin/bash
url="${@: -1}"
if [ "$url" = "$DEPLOY_HEALTH_URL" ]; then
  commit=$(cat "$DEPLOY_APP_DIR/.deploy-commit" 2>/dev/null)
  echo "health @ $commit" >> "$DEPLOY_LOG"
  if [ -n "$FAKE_BAD_COMMIT" ] && [ "$commit" = "$FAKE_BAD_COMMIT" ]; then
    printf 000; exit 7
  fi
fi
printf 200
""",
    "sleep": "#!/bin/bash\nexit 0\n",
}


def git(cwd, *args):
    return subprocess.run(
        [GIT, *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def commit_file(repo, name, content, message):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Origin with two commits on main and one on a side branch; the server
    checkout sits on the first commit."""
    for key, value in {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
    }.items():
        monkeypatch.setenv(key, value)

    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(origin), str(work))
    git(work, "checkout", "-q", "-b", "main")
    (work / ".gitignore").write_text(".env\nbackend/.deploy-commit\n")
    commit_file(work, "backend/scripts/check_config.py", "# CHECK v1\n", "c1")
    c1 = commit_file(work, "backend/app.txt", "v1\n", "app v1")
    git(work, "push", "-q", "origin", "main")

    server = tmp_path / "server"
    git(tmp_path, "clone", "-q", str(origin), str(server))
    (server / "backend" / ".env").write_text("SECRET_KEY=x\n")

    c2 = commit_file(work, "backend/app.txt", "v2\n", "app v2")
    git(work, "push", "-q", "origin", "main")
    git(work, "checkout", "-q", "-b", "side")
    side = commit_file(work, "backend/app.txt", "side\n", "side")
    git(work, "push", "-q", "origin", "side")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in FAKES.items():
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)

    log = tmp_path / "deploy.log"
    run_env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "USER": "deploy",
        "DEPLOY_LOG": str(log),
        "DEPLOY_APP_DIR": str(server / "backend"),
        "DEPLOY_DASHBOARD_DIR": str(tmp_path / "no-dashboard"),
        "DEPLOY_BACKUP_DIR": str(tmp_path / "backups"),
        "DEPLOY_HEALTH_URL": "http://localhost:8000/health",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    return {
        "c1": c1, "c2": c2, "side": side, "server": server,
        "log": log, "env": run_env, "tmp": tmp_path,
    }


def deploy(ctx, *args, **extra):
    env = {**ctx["env"], **extra}
    result = subprocess.run(
        [BASH, str(DEPLOY), *args], env=env, capture_output=True, text=True, timeout=60
    )
    log = ctx["log"].read_text().splitlines() if ctx["log"].exists() else []
    return result, log


def head(ctx):
    return git(ctx["server"], "rev-parse", "HEAD")


def index_of(log, prefix):
    for i, line in enumerate(log):
        if line.startswith(prefix):
            return i
    raise AssertionError(f"{prefix!r} not in log:\n" + "\n".join(log))


def deployed_commit_file(ctx):
    return (ctx["server"] / "backend" / ".deploy-commit").read_text().strip()


def test_happy_path_order_and_exact_commit(env):
    result, log = deploy(env, env["c2"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert head(env) == env["c2"]
    assert deployed_commit_file(env) == env["c2"]

    # The pre-change config check runs the TARGET commit's script on the old code.
    first_check = index_of(log, "config-check-current-code")
    assert "CHECK v1" in log[first_check] and log[first_check].endswith(env["c1"])
    order = [
        first_check,
        index_of(log, "pg_dump"),
        index_of(log, "install @ " + env["c2"]),
        index_of(log, "config-check-new-code @ " + env["c2"]),
        index_of(log, "migrate @ " + env["c2"]),
        index_of(log, "systemctl restart rmirror @ " + env["c2"]),
        index_of(log, "health @ " + env["c2"]),
    ]
    assert order == sorted(order), log
    assert list((env["tmp"] / "backups").glob("rmirror_*.sql.gz"))
    # Detached at the exact commit, not on a branch.
    assert git(env["server"], "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"


def test_sha_from_env_var(env):
    result, _ = deploy(env, DEPLOY_SHA=env["c2"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert head(env) == env["c2"]


def test_without_sha_deploys_origin_main_with_warning(env):
    result, _ = deploy(env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert head(env) == env["c2"]
    assert "No commit SHA given" in result.stdout


def test_missing_config_aborts_before_any_change(env):
    result, log = deploy(env, env["c2"], FAKE_CONFIG_FAIL="1")
    assert result.returncode != 0
    assert "SECRET_KEY" in result.stdout
    assert head(env) == env["c1"]
    assert not any(line.startswith(("migrate", "install", "pg_dump", "systemctl")) for line in log)


def test_failing_migration_rolls_back_to_previous_commit(env):
    result, log = deploy(env, env["c2"], FAKE_MIGRATE_FAIL="1")
    assert result.returncode != 0
    assert head(env) == env["c1"]
    assert deployed_commit_file(env) == env["c1"]
    migrate = index_of(log, "migrate @ " + env["c2"])
    reinstall = index_of(log, "install @ " + env["c1"])
    restart = index_of(log, "systemctl restart rmirror @ " + env["c1"])
    assert migrate < reinstall < restart
    assert "systemctl restart rmirror @ " + env["c2"] not in log
    # Warns that the schema may be ahead, names the dump, never downgrades.
    assert "AHEAD of the running code" in result.stdout
    backup = next((env["tmp"] / "backups").glob("rmirror_*.sql.gz"))
    assert str(backup) in result.stdout
    assert not any("downgrade" in line for line in log)


def test_failing_health_check_rolls_back(env):
    result, log = deploy(env, env["c2"], FAKE_BAD_COMMIT=env["c2"])
    assert result.returncode != 0
    assert head(env) == env["c1"]
    assert deployed_commit_file(env) == env["c1"]
    bad_restart = index_of(log, "systemctl restart rmirror @ " + env["c2"])
    good_restart = index_of(log, "systemctl restart rmirror @ " + env["c1"])
    assert bad_restart < good_restart
    # Polled for the full window (30 attempts) before giving up.
    assert sum(1 for line in log if line == "health @ " + env["c2"]) == 30
    assert "healthy on the previous code" in result.stdout
    assert "Pre-deploy dump" in result.stdout


@pytest.mark.parametrize(
    "arg",
    ["0123456789abcdef0123456789abcdef01234567", "feature-branch", "HEAD~1"],
)
def test_unknown_or_invalid_sha_refused(env, arg):
    result, log = deploy(env, arg)
    assert result.returncode != 0
    assert "Refusing" in result.stdout or "Not a commit SHA" in result.stdout
    assert head(env) == env["c1"]
    assert log == []


def test_commit_not_on_main_refused(env):
    result, log = deploy(env, env["side"])
    assert result.returncode != 0
    assert "not on origin/main" in result.stdout
    assert head(env) == env["c1"]
    assert log == []


def test_every_sudo_command_is_in_the_sudoers_list(env):
    # The failing-health run exercises restart, is-active and journalctl.
    _, log = deploy(env, env["c2"], FAKE_BAD_COMMIT=env["c2"])
    sudoers = subprocess.run(
        [BASH, str(SUDOERS), "--print"], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    allowed = set()
    for line in sudoers:
        m = re.match(r"deploy ALL=\((\w+)\) NOPASSWD: /usr/bin/(.+)$", line)
        if m:
            allowed.add((m.group(1), m.group(2)))
    used = [line[len("sudo "):] for line in log if line.startswith("sudo ")]
    assert used
    for cmd in used:
        runas = "root"
        if cmd.startswith("-u "):
            _, runas, cmd = cmd.split(" ", 2)
        assert (runas, cmd) in allowed, f"sudo {cmd} (as {runas}) not in sudoers"
