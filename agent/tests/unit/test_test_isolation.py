"""Guard: the test suite must never write to the developer's real config."""

from app.config import Config
from app.sync.manifest import UploadManifest
from tests.conftest import REAL_CONFIG_DIRS, REAL_HOME


def _snapshot(dirs) -> dict:
    """Path -> (size, mtime) for every file in the given directories."""
    snap = {}
    for d in dirs:
        if d.is_dir():
            for p in d.rglob("*"):
                if p.is_file():
                    st = p.stat()
                    snap[p] = (st.st_size, st.st_mtime_ns)
    return snap


def test_default_config_path_is_inside_isolated_home(isolated_home):
    path = Config.get_default_config_path()
    assert path.is_relative_to(isolated_home)
    assert not path.is_relative_to(REAL_HOME)


def test_save_without_path_does_not_touch_real_config(test_config, isolated_home):
    before = _snapshot(REAL_CONFIG_DIRS)

    test_config.save()

    assert (isolated_home / ".config/rmirror/config.yaml").exists()
    assert UploadManifest.for_config(test_config).db_path.is_relative_to(isolated_home)
    assert _snapshot(REAL_CONFIG_DIRS) == before
