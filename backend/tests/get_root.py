"""foundation.get_root: one import-location-independent project root."""

import foundation.paths as paths
from foundation import get_root


def test_get_root_points_at_a_marker_dir():
    get_root.cache_clear()
    root = get_root()
    assert root.is_dir()
    assert any((root / m).exists() for m in paths._MARKERS)


def test_get_root_is_stable_regardless_of_cwd(tmp_path, monkeypatch):
    get_root.cache_clear()
    first = get_root()
    get_root.cache_clear()
    monkeypatch.chdir(tmp_path)   # caller's cwd must not change the answer
    try:
        assert get_root() == first
    finally:
        get_root.cache_clear()


def test_vraksha_root_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("VRAKSHA_ROOT", str(tmp_path))
    get_root.cache_clear()
    try:
        assert get_root() == tmp_path.resolve()
    finally:
        get_root.cache_clear()
