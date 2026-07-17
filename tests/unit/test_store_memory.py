import pytest

from redthread.store import LocalStore


def _store(tmp_path):
    return LocalStore.init(tmp_path / "store", project_id="demo", phases=["build"])


def test_memory_write_read_roundtrip(tmp_path):
    store = _store(tmp_path)
    store.memory_write("agent-notes", "preferences.md", "# Preferences\n\nUse uv.\n")
    assert store.memory_read("agent-notes", "preferences.md") == "# Preferences\n\nUse uv.\n"


def test_memory_read_missing_returns_none(tmp_path):
    store = _store(tmp_path)
    assert store.memory_read("agent-notes", "missing.md") is None


def test_memory_list_returns_sorted_relative_keys(tmp_path):
    store = _store(tmp_path)
    store.memory_write("agent-notes", "b.md", "b")
    store.memory_write("agent-notes", "a.md", "a")
    store.memory_write("agent-notes", "sub/c.md", "c")
    assert store.memory_list("agent-notes") == ["a.md", "b.md", "sub/c.md"]


def test_memory_list_unknown_namespace_returns_empty(tmp_path):
    store = _store(tmp_path)
    assert store.memory_list("never-used") == []


@pytest.mark.parametrize("namespace", ["..", ".", "a/b", "a\\b", ""])
def test_memory_rejects_unsafe_namespace(tmp_path, namespace):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.memory_write(namespace, "k.md", "x")


@pytest.mark.parametrize("key", ["../escape.md", "/etc/passwd", "a\\..\\b", "", "../../x"])
def test_memory_rejects_unsafe_key(tmp_path, key):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.memory_write("agent-notes", key, "x")


def test_memory_key_cannot_escape_namespace_dir(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.memory_write("agent-notes", "../../outside.md", "x")
    escape_target = tmp_path / "outside.md"
    assert not escape_target.exists()
