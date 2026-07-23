from pathlib import Path

import pytest

from redthread.mcp import tools
from redthread.store import LocalStore, StoreError


def _store(tmp_path):
    return LocalStore.init(tmp_path / "store", project_id="demo", phases=["build", "test"])


def test_run_start_and_list(tmp_path):
    store = _store(tmp_path)
    record = tools.run_start(store)
    assert record["run_id"] in tools.run_list(store)


def test_context_log_and_read_roundtrip(tmp_path):
    store = _store(tmp_path)
    run_id = tools.run_start(store)["run_id"]
    entry_id = tools.context_log(store, run_id, "build", "note", payload={"msg": "hi"})

    entries = tools.context_read(store, run_id, phase="build")
    assert entries[0]["entry_id"] == entry_id
    assert entries[0]["payload"] == {"msg": "hi"}


def test_artifact_put_and_get_roundtrip(tmp_path):
    store = _store(tmp_path)
    run_id = tools.run_start(store)["run_id"]
    source = tmp_path / "f.txt"
    source.write_text("payload", encoding="utf-8")

    put = tools.artifact_put(store, run_id, "build", str(source), kind="log")
    got = tools.artifact_get(store, run_id, put["artifact_id"])
    assert got["artifact"]["sha256"] == put["sha256"]
    assert Path(got["path"]).read_text(encoding="utf-8") == "payload"


def test_summary_update_and_get(tmp_path):
    store = _store(tmp_path)
    run_id = tools.run_start(store)["run_id"]
    tools.summary_update(store, run_id, "build", "# hi\n")
    assert tools.summary_get(store, run_id, "build") == "# hi\n"


def test_handoff_publish_and_get_roundtrip(tmp_path):
    store = _store(tmp_path)
    run_id = tools.run_start(store)["run_id"]
    published = tools.handoff_publish(
        store, run_id, "build", headline="build ok", key_results={"warnings": 0}
    )
    fetched = tools.handoff_get(store, run_id, "build")
    assert fetched == published


def test_memory_write_read_list_roundtrip(tmp_path):
    store = _store(tmp_path)
    tools.memory_write(store, "agent", "notes.md", "remember this")
    assert tools.memory_read(store, "agent", "notes.md") == "remember this"
    assert tools.memory_list(store, "agent") == ["notes.md"]


def test_context_log_rejects_phase_outside_pipeline(tmp_path):
    store = _store(tmp_path)
    run_id = tools.run_start(store)["run_id"]
    with pytest.raises(StoreError):
        tools.context_log(store, run_id, "deploy", "note")


def test_agents_md_bootstrap_creates_file_when_none_exists(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    result = tools.agents_md_bootstrap(tmp_path / "store", project_dir)

    assert result == {"status": "created", "file": str(project_dir / "AGENTS.md")}
    text = (project_dir / "AGENTS.md").read_text(encoding="utf-8")
    assert "## Agent memory (Redthread)" in text
    assert str(tmp_path / "store") in text


def test_agents_md_bootstrap_appends_to_existing_agents_md(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "AGENTS.md").write_text("# Existing notes\n", encoding="utf-8")

    result = tools.agents_md_bootstrap(tmp_path / "store", project_dir)

    assert result["status"] == "appended"
    text = (project_dir / "AGENTS.md").read_text(encoding="utf-8")
    assert text.startswith("# Existing notes\n")
    assert "## Agent memory (Redthread)" in text


def test_agents_md_bootstrap_prefers_existing_claude_md_over_creating_agents_md(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "CLAUDE.md").write_text("# Claude notes\n", encoding="utf-8")

    result = tools.agents_md_bootstrap(tmp_path / "store", project_dir)

    assert result["file"] == str(project_dir / "CLAUDE.md")
    assert not (project_dir / "AGENTS.md").exists()


def test_agents_md_bootstrap_is_idempotent(tmp_path):
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    first = tools.agents_md_bootstrap(tmp_path / "store", project_dir)
    assert first["status"] == "created"
    text_after_first = (project_dir / "AGENTS.md").read_text(encoding="utf-8")

    second = tools.agents_md_bootstrap(tmp_path / "store", project_dir)
    assert second == {"status": "already_present", "file": str(project_dir / "AGENTS.md")}
    assert (project_dir / "AGENTS.md").read_text(encoding="utf-8") == text_after_first
