from typer.testing import CliRunner

from redthread.cli import app

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
