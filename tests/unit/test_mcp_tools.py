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
    logged = tools.context_log(store, "build", "note", payload={"msg": "hi"}, run_id=run_id)

    read = tools.context_read(store, phase="build", run_id=run_id)
    assert read["run_id"] == run_id
    assert read["count"] == 1
    assert read["entries"][0]["entry_id"] == logged["entry_id"]
    assert read["entries"][0]["payload"] == {"msg": "hi"}


def test_artifact_put_and_get_roundtrip(tmp_path):
    store = _store(tmp_path)
    run_id = tools.run_start(store)["run_id"]
    source = tmp_path / "f.txt"
    source.write_text("payload", encoding="utf-8")

    put = tools.artifact_put(store, "build", str(source), kind="log", run_id=run_id)
    got = tools.artifact_get(store, put["artifact_id"], run_id=run_id)
    assert got["artifact"]["sha256"] == put["sha256"]
    assert Path(got["path"]).read_text(encoding="utf-8") == "payload"


def test_summary_update_and_get(tmp_path):
    store = _store(tmp_path)
    run_id = tools.run_start(store)["run_id"]
    tools.summary_update(store, "build", "# hi\n", run_id=run_id)
    assert tools.summary_get(store, "build", run_id=run_id)["markdown"] == "# hi\n"


def test_handoff_publish_and_get_roundtrip(tmp_path):
    store = _store(tmp_path)
    run_id = tools.run_start(store)["run_id"]
    published = tools.handoff_publish(
        store, "build", headline="build ok", key_results={"warnings": 0}, run_id=run_id
    )
    fetched = tools.handoff_get(store, "build", run_id=run_id)
    assert fetched == published


def test_memory_write_read_list_roundtrip(tmp_path):
    store = _store(tmp_path)
    written = tools.memory_write(store, "agent", "notes.md", "remember this")
    assert written["key"] == "notes.md"
    assert tools.memory_read(store, "agent", "notes.md") == "remember this"

    index = tools.memory_list(store, "agent")
    assert [i["key"] for i in index] == ["notes.md"]
    assert index[0]["description"] == "remember this"


def test_memory_list_describes_entries_and_spans_namespaces(tmp_path):
    store = _store(tmp_path)
    tools.memory_write(store, "notes", "a.md", "body", description="a conventions note")
    tools.memory_write(store, "sessions", "b.md", "body")

    index = tools.memory_list(store)
    assert {i["namespace"] for i in index} == {"notes", "sessions"}
    assert next(i for i in index if i["key"] == "a.md")["description"] == "a conventions note"


def test_memory_search_finds_entry_by_body(tmp_path):
    store = _store(tmp_path)
    tools.memory_write(store, "notes", "a.md", "we chose rsync for blobs")

    hits = tools.memory_search(store, "rsync")
    assert [h["key"] for h in hits] == ["a.md"]
    assert "rsync" in hits[0]["match"]


def test_context_log_rejects_phase_outside_pipeline(tmp_path):
    store = _store(tmp_path)
    run_id = tools.run_start(store)["run_id"]
    with pytest.raises(StoreError):
        tools.context_log(store, "deploy", "note", run_id=run_id)


# ---- context_bootstrap ---------------------------------------------------


def test_context_bootstrap_on_an_empty_store_reports_no_run_and_no_memory(tmp_path):
    store = _store(tmp_path)
    payload = tools.context_bootstrap(store)

    assert payload["project"] == {"project_id": "demo", "name": None, "phases": ["build", "test"]}
    assert payload["current_run"] is None
    assert payload["runs"] == {"total": 0, "recent": []}
    assert payload["memory"] == {"namespaces": [], "total": 0, "entries": []}
    assert "run_start" in payload["_next"]
    assert "no long-term memory yet" in payload["_next"]


def test_context_bootstrap_surfaces_runs_memory_handoffs_and_summaries(tmp_path):
    store = _store(tmp_path)
    run_id = tools.run_start(store)["run_id"]
    tools.summary_update(store, "build", "# built\n")
    tools.handoff_publish(store, "build", headline="build ok")
    tools.memory_write(store, "notes", "uv.md", "body", description="Toolchain choice")

    payload = tools.context_bootstrap(store)

    assert payload["current_run"] == run_id
    assert payload["runs"]["total"] == 1
    assert payload["runs"]["recent"][0]["run_id"] == run_id
    assert payload["runs"]["recent"][0]["status"] == "active"
    assert payload["handoffs"] == [{"phase": "build", "headline": "build ok"}]
    assert payload["summaries"] == ["build"]
    assert payload["memory"]["namespaces"] == ["notes"]
    assert payload["memory"]["entries"][0]["description"] == "Toolchain choice"
    assert run_id in payload["_next"]


def test_context_bootstrap_lists_recent_runs_newest_first_within_limit(tmp_path):
    store = _store(tmp_path)
    run_ids = [tools.run_start(store)["run_id"] for _ in range(4)]

    payload = tools.context_bootstrap(store, recent_runs=2)

    assert payload["runs"]["total"] == 4
    assert [r["run_id"] for r in payload["runs"]["recent"]] == run_ids[::-1][:2]


def test_context_bootstrap_caps_the_memory_index(tmp_path):
    store = _store(tmp_path)
    for i in range(5):
        tools.memory_write(store, "notes", f"{i}.md", "body")

    payload = tools.context_bootstrap(store, memory_limit=2)
    assert payload["memory"]["total"] == 5
    assert len(payload["memory"]["entries"]) == 2


def test_context_bootstrap_accepts_an_explicit_run(tmp_path):
    store = _store(tmp_path)
    older = tools.run_start(store)["run_id"]
    tools.run_start(store)
    tools.handoff_publish(store, "build", headline="older build", run_id=older)

    payload = tools.context_bootstrap(store, run_id=older)
    assert payload["current_run"] == older
    assert payload["handoffs"] == [{"phase": "build", "headline": "older build"}]


# ---- implicit current run ------------------------------------------------


def test_run_scoped_tools_default_to_the_active_run(tmp_path):
    store = _store(tmp_path)
    run_id = tools.run_start(store)["run_id"]

    logged = tools.context_log(store, "build", "note", payload={"msg": "hi"})
    assert logged["run_id"] == run_id

    read = tools.context_read(store, phase="build")
    assert read["run_id"] == run_id
    assert read["entries"][0]["entry_id"] == logged["entry_id"]


def test_omitted_run_id_resolves_to_the_newest_active_run(tmp_path):
    store = _store(tmp_path)
    tools.run_start(store)
    newest = tools.run_start(store)["run_id"]

    assert tools.resolve_run_id(store, None) == newest
    assert tools.context_log(store, "build", "note")["run_id"] == newest


def test_omitted_run_id_skips_runs_that_are_no_longer_active(tmp_path):
    store = _store(tmp_path)
    older = tools.run_start(store)["run_id"]
    newer = tools.run_start(store)["run_id"]

    record = store.get_run(newer)
    record.status = "done"
    store.save_run(record)

    assert tools.resolve_run_id(store, None) == older


def test_explicit_run_id_always_wins(tmp_path):
    store = _store(tmp_path)
    older = tools.run_start(store)["run_id"]
    tools.run_start(store)

    assert tools.resolve_run_id(store, older) == older


def test_resolve_run_id_without_any_active_run_says_what_to_do(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(StoreError, match="run_start"):
        tools.resolve_run_id(store, None)


# ---- agents_md_bootstrap -------------------------------------------------


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
