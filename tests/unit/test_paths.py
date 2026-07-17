import pytest

from redthread.paths import PathsMap


def test_set_get_persists_across_instances(tmp_path):
    target = tmp_path / "objects"
    PathsMap(tmp_path / "config").set("objects", target)
    reopened = PathsMap(tmp_path / "config")
    assert reopened.get("objects") == target


def test_get_unset_backend_returns_none(tmp_path):
    assert PathsMap(tmp_path / "config").get("nope") is None


def test_open_backend_requires_configuration(tmp_path):
    with pytest.raises(KeyError):
        PathsMap(tmp_path / "config").open_backend("unconfigured")


def test_open_backend_returns_working_rsync_backend(tmp_path):
    paths = PathsMap(tmp_path / "config")
    paths.set("objects", tmp_path / "objects-dir")
    backend = paths.open_backend("objects")
    source = tmp_path / "a.bin"
    source.write_bytes(b"x")
    digest = backend.put(source)
    assert backend.exists(digest)
