from pathlib import Path

import pytest

from redthread import memory_port


def _write(path: Path, text: str = "note\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ---- discover ------------------------------------------------------------


def test_discover_returns_the_file_itself_for_a_file_source(tmp_path):
    target = _write(tmp_path / "one.md")
    assert memory_port.discover(target) == [target]


def test_discover_finds_text_files_recursively_and_sorts_them(tmp_path):
    _write(tmp_path / "b.md")
    _write(tmp_path / "a.txt")
    _write(tmp_path / "nested" / "c.markdown")

    found = memory_port.discover(tmp_path)

    assert [p.name for p in found] == ["a.txt", "b.md", "c.markdown"]


def test_discover_without_recursion_stays_at_the_top_level(tmp_path):
    _write(tmp_path / "top.md")
    _write(tmp_path / "nested" / "deep.md")

    found = memory_port.discover(tmp_path, recursive=False)

    assert [p.name for p in found] == ["top.md"]


def test_discover_skips_hidden_files_and_directories(tmp_path):
    _write(tmp_path / "keep.md")
    _write(tmp_path / ".hidden.md")
    _write(tmp_path / ".git" / "config.md")

    assert [p.name for p in memory_port.discover(tmp_path)] == ["keep.md"]


def test_discover_skips_non_text_extensions(tmp_path):
    _write(tmp_path / "keep.md")
    _write(tmp_path / "diagram.png")

    assert [p.name for p in memory_port.discover(tmp_path)] == ["keep.md"]


def test_discover_returns_nothing_for_a_missing_path(tmp_path):
    assert memory_port.discover(tmp_path / "nope") == []


# ---- key_for -------------------------------------------------------------


def test_key_for_drops_the_extension(tmp_path):
    path = _write(tmp_path / "2026-01-01_thing.md")
    assert memory_port.key_for(path, tmp_path) == "2026-01-01_thing"


def test_key_for_preserves_nesting_under_the_source_root(tmp_path):
    path = _write(tmp_path / "decisions" / "db.md")
    assert memory_port.key_for(path, tmp_path) == "decisions/db"


def test_key_for_uses_only_the_filename_when_the_source_is_a_file(tmp_path):
    path = _write(tmp_path / "deep" / "one.md")
    assert memory_port.key_for(path, path) == "one"


def test_key_for_replaces_unsafe_characters(tmp_path):
    path = _write(tmp_path / "my notes (draft)!.md")
    assert memory_port.key_for(path, tmp_path) == "my-notes-draft"


def test_key_for_cannot_escape_the_namespace(tmp_path):
    # A segment that slugs down to nothing is dropped, never emitted as a
    # traversal — the worst case is a lost segment, not a write outside.
    path = _write(tmp_path / "..." / "real.md")
    assert memory_port.key_for(path, tmp_path) == "real"


def test_key_for_rejects_a_name_with_nothing_usable_left(tmp_path):
    path = _write(tmp_path / "!!!.md")
    with pytest.raises(ValueError, match="cannot derive a memory key"):
        memory_port.key_for(path, tmp_path)
