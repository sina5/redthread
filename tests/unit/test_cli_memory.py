import subprocess
from pathlib import Path

from typer.testing import CliRunner

from redthread.cli import app
from redthread.store import gitio

runner = CliRunner()


def test_memory_write_read_list_roundtrip(tmp_path):
    store = str(tmp_path / "store")
    runner.invoke(app, ["init", "demo", "--phases", "build", "--store", store])

    note = tmp_path / "note.md"
    note.write_text("# hello\n\nsome content\n", encoding="utf-8")

    result = runner.invoke(
        app, ["memory", "write", "sessions", "note.md", str(note), "--store", store]
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["memory", "read", "sessions", "note.md", "--store", store])
    assert result.exit_code == 0, result.output
    assert "some content" in result.output

    result = runner.invoke(app, ["memory", "list", "sessions", "--store", store])
    assert result.exit_code == 0, result.output
    assert "note.md" in result.output


def test_memory_read_missing_key_exits_nonzero(tmp_path):
    store = str(tmp_path / "store")
    runner.invoke(app, ["init", "demo", "--phases", "build", "--store", store])
    result = runner.invoke(app, ["memory", "read", "sessions", "nope.md", "--store", store])
    assert result.exit_code != 0


def test_memory_write_rejects_path_traversal(tmp_path):
    store = str(tmp_path / "store")
    runner.invoke(app, ["init", "demo", "--phases", "build", "--store", store])
    note = tmp_path / "note.md"
    note.write_text("x", encoding="utf-8")
    result = runner.invoke(
        app, ["memory", "write", "sessions", "../escape.md", str(note), "--store", store]
    )
    assert result.exit_code != 0


def test_memory_import_reports_each_entry_and_a_tally(tmp_path):
    store = str(tmp_path / "store")
    runner.invoke(app, ["init", "demo", "--phases", "build", "--store", store])
    source = tmp_path / "old-memory"
    (source / "decisions").mkdir(parents=True)
    (source / "sqlite.md").write_text("# Chose SQLite\n", encoding="utf-8")
    (source / "decisions" / "db.md").write_text("nested\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["memory", "import", str(source), "--namespace", "ported", "--no-push", "--store", store],
    )
    assert result.exit_code == 0, result.output
    assert "imported\tported/sqlite" in result.output
    assert "imported\tported/decisions/db" in result.output
    assert "2 imported, 0 skipped, 0 failed" in result.output

    # Re-running is a no-op rather than a rewrite.
    result = runner.invoke(
        app,
        ["memory", "import", str(source), "--namespace", "ported", "--no-push", "--store", store],
    )
    assert result.exit_code == 0, result.output
    assert "0 imported, 2 skipped, 0 failed" in result.output


def test_memory_import_missing_source_exits_nonzero(tmp_path):
    store = str(tmp_path / "store")
    runner.invoke(app, ["init", "demo", "--phases", "build", "--store", store])
    result = runner.invoke(
        app, ["memory", "import", str(tmp_path / "nope"), "--no-push", "--store", store]
    )
    assert result.exit_code != 0


def test_memory_write_pushes_by_default_and_no_push_opts_out(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    store = str(tmp_path / "store")
    runner.invoke(app, ["init", "demo", "--phases", "build", "--store", store])
    gitio.configure_identity(Path(store), "Test", "test@example.com")
    gitio.set_remote(Path(store), str(remote))

    note = tmp_path / "note.md"
    note.write_text("some content\n", encoding="utf-8")

    result = runner.invoke(
        app, ["memory", "write", "sessions", "note.md", str(note), "--store", store]
    )
    assert result.exit_code == 0, result.output
    assert "pushed" in result.output
    assert not gitio.is_dirty(Path(store))

    note.write_text("edited\n", encoding="utf-8")
    result = runner.invoke(
        app, ["memory", "write", "sessions", "note.md", str(note), "--no-push", "--store", store]
    )
    assert result.exit_code == 0, result.output
    # --no-push declines the network step only: the entry is still committed,
    # because nobody passing --no-push is asking to lose their data.
    assert "committed" in result.output
    assert "push skipped" in result.output
    assert not gitio.is_dirty(Path(store))


def test_memory_list_marks_entries_that_are_not_committed(tmp_path):
    """`memory list` is what an agent reaches for to confirm a write worked,
    so it has to tell "saved" apart from "saved and durable"."""
    store = tmp_path / "store"
    runner.invoke(app, ["init", "demo", "--phases", "build", "--store", str(store)])
    gitio.configure_identity(store, "Test", "test@example.com")
    (store / "memory" / "notes").mkdir(parents=True, exist_ok=True)
    (store / "memory" / "notes" / "stray.md").write_text("untracked\n", encoding="utf-8")

    result = runner.invoke(app, ["memory", "list", "--store", str(store)])

    assert result.exit_code == 0, result.output
    assert "* notes/stray.md" in result.output
    assert "uncommitted" in result.output

    runner.invoke(app, ["sync", "--store", str(store)])
    result = runner.invoke(app, ["memory", "list", "--store", str(store)])
    assert "* notes/stray.md" not in result.output
    assert "notes/stray.md" in result.output


def test_status_reports_durability_of_the_store(tmp_path):
    store = tmp_path / "store"
    runner.invoke(app, ["init", "demo", "--phases", "build", "--store", str(store)])
    gitio.configure_identity(store, "Test", "test@example.com")

    result = runner.invoke(app, ["status", "--store", str(store)])

    assert result.exit_code == 0, result.output
    assert "publishes" in result.output
    assert "remote\t(none)" in result.output

    (store / "memory" / "notes").mkdir(parents=True, exist_ok=True)
    (store / "memory" / "notes" / "stray.md").write_text("untracked\n", encoding="utf-8")
    result = runner.invoke(app, ["status", "--store", str(store)])
    assert "notes/stray.md" in result.output
